#!/usr/bin/env python3
"""
Lightning HTLC Analyzer - Detect missed routing opportunities

Similar to lightning-jet's htlc-analyzer, this tool identifies missed routing
opportunities by analyzing HTLC failures and forwarding patterns.
"""

import asyncio
import logging
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.monitoring.htlc_monitor import HTLCMonitor
from src.monitoring.opportunity_analyzer import OpportunityAnalyzer
from src.api.client import LndManageClient
from src.experiment.lnd_grpc_client import AsyncLNDgRPCClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console()


async def monitor_htlcs_realtime(grpc_client, lnd_manage_client, duration_hours: int = 24):
    """Monitor HTLCs in real-time and detect opportunities"""
    console.print(f"\n[bold green]Starting HTLC monitoring for {duration_hours} hours...[/bold green]\n")

    monitor = HTLCMonitor(
        grpc_client=grpc_client,
        history_hours=duration_hours,
        min_failure_count=3,
        min_missed_sats=100
    )

    # Start monitoring
    await monitor.start_monitoring()

    try:
        # Run for specified duration
        end_time = datetime.utcnow() + timedelta(hours=duration_hours)

        while datetime.utcnow() < end_time:
            await asyncio.sleep(60)  # Check every minute

            # Display stats
            stats = monitor.get_summary_stats()
            console.print(f"\n[cyan]Monitoring Status:[/cyan]")
            console.print(f"  Events tracked: {stats['total_events']}")
            console.print(f"  Total failures: {stats['total_failures']}")
            console.print(f"  Liquidity failures: {stats['liquidity_failures']}")
            console.print(f"  Channels: {stats['channels_tracked']}")
            console.print(f"  Missed revenue: {stats['total_missed_revenue_sats']:.2f} sats")

            # Cleanup old data every hour
            if datetime.utcnow().minute == 0:
                monitor.cleanup_old_data()

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping monitoring...[/yellow]")
    finally:
        await monitor.stop_monitoring()

    # Analyze opportunities
    console.print("\n[bold]Analyzing opportunities...[/bold]\n")
    analyzer = OpportunityAnalyzer(monitor, lnd_manage_client)
    opportunities = await analyzer.analyze_opportunities()

    if opportunities:
        display_opportunities(opportunities)
        return opportunities
    else:
        console.print("[yellow]No significant routing opportunities detected.[/yellow]")
        return []


async def analyze_forwarding_history(grpc_client, lnd_manage_client, hours: int = 24):
    """Analyze historical forwarding data for missed opportunities"""
    console.print(f"\n[bold green]Analyzing forwarding history (last {hours} hours)...[/bold green]\n")

    # Get forwarding history
    start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())
    end_time = int(datetime.utcnow().timestamp())

    try:
        forwards = await grpc_client.get_forwarding_history(
            start_time=start_time,
            end_time=end_time,
            num_max_events=10000
        )

        console.print(f"Found {len(forwards)} forwarding events")

        # Group by channel and analyze
        channel_stats = {}
        for fwd in forwards:
            chan_out = str(fwd['chan_id_out'])
            if chan_out not in channel_stats:
                channel_stats[chan_out] = {
                    'forwards': 0,
                    'total_volume_msat': 0,
                    'total_fees_msat': 0
                }
            channel_stats[chan_out]['forwards'] += 1
            channel_stats[chan_out]['total_volume_msat'] += fwd['amt_out_msat']
            channel_stats[chan_out]['total_fees_msat'] += fwd['fee_msat']

        # Display top routing channels
        display_forwarding_stats(channel_stats)

        return channel_stats

    except Exception as e:
        logger.error(f"Failed to analyze forwarding history: {e}")
        return {}


def display_opportunities(opportunities):
    """Display opportunities in a nice table"""
    console.print("\n[bold cyan]MISSED ROUTING OPPORTUNITIES[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Channel", width=20)
    table.add_column("Peer", width=20)
    table.add_column("Failures", justify="right", width=10)
    table.add_column("Missed Revenue", justify="right", width=15)
    table.add_column("Potential/Month", justify="right", width=15)
    table.add_column("Urgency", justify="right", width=8)
    table.add_column("Recommendation", width=30)

    for i, opp in enumerate(opportunities[:20], 1):
        urgency_style = "red" if opp.urgency_score > 70 else "yellow" if opp.urgency_score > 40 else "green"

        table.add_row(
            str(i),
            opp.channel_id[:16] + "...",
            opp.peer_alias or "Unknown",
            str(opp.total_failures),
            f"{opp.missed_revenue_sats:.2f} sats",
            f"{opp.potential_monthly_revenue_sats:.0f} sats",
            f"[{urgency_style}]{opp.urgency_score:.0f}[/{urgency_style}]",
            opp.recommendation_type.replace('_', ' ').title()
        )

    console.print(table)

    # Summary
    total_missed = sum(o.missed_revenue_sats for o in opportunities)
    total_potential = sum(o.potential_monthly_revenue_sats for o in opportunities)

    summary = f"""
[bold]Summary[/bold]
Total opportunities: {len(opportunities)}
Missed revenue: {total_missed:.2f} sats
Potential monthly revenue: {total_potential:.0f} sats/month
    """
    console.print(Panel(summary.strip(), title="Opportunity Summary", border_style="green"))


def display_forwarding_stats(channel_stats):
    """Display forwarding statistics"""
    console.print("\n[bold cyan]TOP ROUTING CHANNELS[/bold cyan]\n")

    # Sort by total fees
    sorted_channels = sorted(
        channel_stats.items(),
        key=lambda x: x[1]['total_fees_msat'],
        reverse=True
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Channel ID", width=20)
    table.add_column("Forwards", justify="right")
    table.add_column("Volume (sats)", justify="right")
    table.add_column("Fees (sats)", justify="right")
    table.add_column("Avg Fee Rate", justify="right")

    for chan_id, stats in sorted_channels[:20]:
        volume_sats = stats['total_volume_msat'] / 1000
        fees_sats = stats['total_fees_msat'] / 1000
        avg_fee_rate = (stats['total_fees_msat'] / max(stats['total_volume_msat'], 1)) * 1_000_000

        table.add_row(
            chan_id[:16] + "...",
            str(stats['forwards']),
            f"{volume_sats:,.0f}",
            f"{fees_sats:.2f}",
            f"{avg_fee_rate:.0f} ppm"
        )

    console.print(table)


@click.group()
def cli():
    """Lightning HTLC Analyzer - Detect missed routing opportunities"""
    pass


@cli.command()
@click.option('--lnd-dir', default='~/.lnd', help='LND directory')
@click.option('--grpc-host', default='localhost:10009', help='LND gRPC host:port')
@click.option('--manage-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--hours', default=24, help='Analysis window in hours')
@click.option('--output', type=click.Path(), help='Output JSON file')
def analyze(lnd_dir, grpc_host, manage_url, hours, output):
    """Analyze forwarding history for missed opportunities"""
    async def run():
        # Connect to LND
        async with AsyncLNDgRPCClient(lnd_dir=lnd_dir, server=grpc_host) as grpc_client:
            async with LndManageClient(manage_url) as lnd_manage:
                # Analyze history
                stats = await analyze_forwarding_history(grpc_client, lnd_manage, hours)

                if output:
                    with open(output, 'w') as f:
                        json.dump(stats, f, indent=2)
                    console.print(f"\n[green]Results saved to {output}[/green]")

    asyncio.run(run())


@cli.command()
@click.option('--lnd-dir', default='~/.lnd', help='LND directory')
@click.option('--grpc-host', default='localhost:10009', help='LND gRPC host:port')
@click.option('--manage-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--duration', default=24, help='Monitoring duration in hours')
@click.option('--output', type=click.Path(), help='Output JSON file')
def monitor(lnd_dir, grpc_host, manage_url, duration, output):
    """Monitor HTLC events in real-time"""
    async def run():
        # Connect to LND
        try:
            async with AsyncLNDgRPCClient(lnd_dir=lnd_dir, server=grpc_host) as grpc_client:
                async with LndManageClient(manage_url) as lnd_manage:
                    # Monitor HTLCs
                    opportunities = await monitor_htlcs_realtime(grpc_client, lnd_manage, duration)

                    if output and opportunities:
                        analyzer = OpportunityAnalyzer(
                            HTLCMonitor(grpc_client),
                            lnd_manage
                        )
                        export_data = await analyzer.export_opportunities_json(opportunities)
                        with open(output, 'w') as f:
                            json.dump(export_data, f, indent=2)
                        console.print(f"\n[green]Results saved to {output}[/green]")

        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            console.print(f"\n[red]Error: {e}[/red]")
            console.print("\n[yellow]Note: HTLC monitoring requires LND 0.14+ with gRPC access[/yellow]")

    asyncio.run(run())


@cli.command()
@click.argument('report_file', type=click.Path(exists=True))
def report(report_file):
    """Generate report from saved opportunity data"""
    with open(report_file, 'r') as f:
        data = json.load(f)

    from src.monitoring.opportunity_analyzer import MissedOpportunity

    opportunities = [
        MissedOpportunity(**opp) for opp in data['opportunities']
    ]

    display_opportunities(opportunities)


if __name__ == '__main__':
    cli()
