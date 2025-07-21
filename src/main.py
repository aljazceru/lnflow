#!/usr/bin/env python3
"""Lightning Fee Optimizer - Main entry point"""

import asyncio
import click
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler

from .api.client import LndManageClient
from .analysis.analyzer import ChannelAnalyzer
from .strategy.optimizer import FeeOptimizer
from .utils.config import Config

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


@click.command()
@click.option('--api-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--config', type=click.Path(exists=True), help='Configuration file path')
@click.option('--analyze-only', is_flag=True, help='Only analyze channels without optimization')
@click.option('--dry-run', is_flag=True, help='Show recommendations without applying them')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--output', '-o', type=click.Path(), help='Output recommendations to file')
def main(
    api_url: str,
    config: Optional[str],
    analyze_only: bool,
    dry_run: bool,
    verbose: bool,
    output: Optional[str]
):
    """Lightning Fee Optimizer - Optimize channel fees for maximum returns"""
    setup_logging(verbose)
    
    console.print("[bold blue]Lightning Fee Optimizer[/bold blue]")
    console.print(f"API URL: {api_url}\n")
    
    try:
        asyncio.run(run_optimizer(
            api_url=api_url,
            config_path=config,
            analyze_only=analyze_only,
            dry_run=dry_run,
            output_path=output
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
    except Exception as e:
        logger.exception("Fatal error occurred")
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise click.Abort()


async def run_optimizer(
    api_url: str,
    config_path: Optional[str],
    analyze_only: bool,
    dry_run: bool,
    output_path: Optional[str]
):
    """Main optimization workflow"""
    config = Config.load(config_path) if config_path else Config()
    
    async with LndManageClient(api_url) as client:
        console.print("[cyan]Checking node status...[/cyan]")
        if not await client.is_synced():
            raise click.ClickException("Node is not synced to chain")
        
        console.print("[cyan]Fetching channel data...[/cyan]")
        response = await client.get_open_channels()
        if isinstance(response, dict) and 'channels' in response:
            channel_ids = response['channels']
        else:
            channel_ids = response if isinstance(response, list) else []
        console.print(f"Found {len(channel_ids)} channels\n")
        
        analyzer = ChannelAnalyzer(client, config)
        console.print("[cyan]Analyzing channel performance...[/cyan]")
        analysis_results = await analyzer.analyze_channels(channel_ids)
        
        if analyze_only:
            analyzer.print_analysis(analysis_results)
            return
        
        optimizer = FeeOptimizer(config)
        console.print("[cyan]Calculating optimal fee strategies...[/cyan]")
        recommendations = optimizer.optimize_fees(analysis_results)
        
        optimizer.print_recommendations(recommendations)
        
        if output_path:
            optimizer.save_recommendations(recommendations, output_path)
            console.print(f"\n[green]Recommendations saved to {output_path}[/green]")
        
        if not dry_run:
            console.print("\n[bold yellow]Note: Automatic fee updates not implemented yet[/bold yellow]")
            console.print("Please review recommendations and apply manually via your node management tool")


if __name__ == "__main__":
    main()