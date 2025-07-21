#!/usr/bin/env python3
"""Lightning Fee Optimization Experiment Runner"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime
import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.experiment.controller import ExperimentController, ExperimentPhase
from src.utils.config import Config

console = Console()
logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Main experiment runner with monitoring and control"""
    
    def __init__(self, lnd_manage_url: str, lnd_rest_url: str, config_path: str = None):
        self.config = Config.load(config_path) if config_path else Config()
        self.controller = ExperimentController(
            config=self.config,
            lnd_manage_url=lnd_manage_url,
            lnd_rest_url=lnd_rest_url
        )
        self.running = False
        self.cycle_count = 0
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('experiment.log'),
                logging.StreamHandler()
            ]
        )
        
        # Handle interrupts gracefully
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        console.print("\n[yellow]Received shutdown signal. Stopping experiment safely...[/yellow]")
        self.running = False
    
    async def run_experiment(self, duration_days: int = 7, collection_interval: int = 30):
        """Run the complete experiment"""
        
        console.print(f"[bold blue]🔬 Lightning Fee Optimization Experiment[/bold blue]")
        console.print(f"Duration: {duration_days} days")
        console.print(f"Data collection interval: {collection_interval} minutes")
        console.print("")
        
        # Initialize experiment
        console.print("[cyan]📊 Initializing experiment...[/cyan]")
        try:
            success = await self.controller.initialize_experiment(duration_days)
            if not success:
                console.print("[red]❌ Failed to initialize experiment[/red]")
                return
        except Exception as e:
            console.print(f"[red]❌ Initialization failed: {e}[/red]")
            return
        
        console.print("[green]✅ Experiment initialized successfully[/green]")
        
        # Display experiment setup
        self._display_experiment_setup()
        
        # Start monitoring loop
        self.running = True
        
        with Live(self._create_status_display(), refresh_per_second=0.2) as live:
            while self.running:
                try:
                    # Run experiment cycle
                    should_continue = await self.controller.run_experiment_cycle()
                    
                    if not should_continue:
                        console.print("\n[green]🎉 Experiment completed successfully![/green]")
                        break
                    
                    self.cycle_count += 1
                    
                    # Update live display
                    live.update(self._create_status_display())
                    
                    # Wait for next collection
                    await asyncio.sleep(collection_interval * 60)
                    
                except Exception as e:
                    logger.error(f"Error in experiment cycle: {e}")
                    console.print(f"[red]❌ Cycle error: {e}[/red]")
                    await asyncio.sleep(60)  # Wait before retry
        
        # Generate final report
        await self._generate_final_report()
    
    def _display_experiment_setup(self):
        """Display experiment setup information"""
        
        group_counts = {}
        for group_name, count in self.controller._get_group_counts().items():
            group_counts[group_name] = count
        
        setup_info = f"""
[bold]Experiment Configuration[/bold]

Start Time: {self.controller.experiment_start.strftime('%Y-%m-%d %H:%M:%S UTC')}
Total Channels: {len(self.controller.experiment_channels)}

Group Distribution:
• Control Group: {group_counts.get('control', 0)} channels (no changes)
• Treatment A: {group_counts.get('treatment_a', 0)} channels (balance optimization)  
• Treatment B: {group_counts.get('treatment_b', 0)} channels (flow optimization)
• Treatment C: {group_counts.get('treatment_c', 0)} channels (advanced strategy)

Safety Limits:
• Max fee increase: {self.controller.MAX_FEE_INCREASE_PCT:.0%}
• Max fee decrease: {self.controller.MAX_FEE_DECREASE_PCT:.0%}
• Max daily changes per channel: {self.controller.MAX_DAILY_CHANGES}
• Rollback triggers: {self.controller.ROLLBACK_REVENUE_THRESHOLD:.0%} revenue drop or {self.controller.ROLLBACK_FLOW_THRESHOLD:.0%} flow reduction
        """
        
        console.print(Panel(setup_info.strip(), title="📋 Experiment Setup"))
    
    def _create_status_display(self):
        """Create live status display"""
        
        current_time = datetime.utcnow()
        if self.controller.experiment_start:
            elapsed_hours = (current_time - self.controller.experiment_start).total_seconds() / 3600
        else:
            elapsed_hours = 0
        
        # Main status table
        status_table = Table(show_header=True, header_style="bold cyan")
        status_table.add_column("Metric", style="white")
        status_table.add_column("Value", style="green")
        
        status_table.add_row("Current Phase", self.controller.current_phase.value.title())
        status_table.add_row("Elapsed Hours", f"{elapsed_hours:.1f}")
        status_table.add_row("Collection Cycles", str(self.cycle_count))
        status_table.add_row("Data Points", str(len(self.controller.data_points)))
        status_table.add_row("Last Collection", current_time.strftime('%H:%M:%S UTC'))
        
        # Recent activity
        recent_changes = 0
        recent_rollbacks = 0
        
        for exp_channel in self.controller.experiment_channels.values():
            # Count changes in last 24 hours
            recent_changes += len([
                change for change in exp_channel.change_history
                if (current_time - datetime.fromisoformat(change['timestamp'])).total_seconds() < 24 * 3600
            ])
            
            # Count rollbacks in last 24 hours  
            recent_rollbacks += len([
                change for change in exp_channel.change_history
                if (current_time - datetime.fromisoformat(change['timestamp'])).total_seconds() < 24 * 3600
                and 'ROLLBACK' in change['reason']
            ])
        
        activity_table = Table(show_header=True, header_style="bold yellow")
        activity_table.add_column("Activity (24h)", style="white")
        activity_table.add_column("Count", style="green")
        
        activity_table.add_row("Fee Changes", str(recent_changes))
        activity_table.add_row("Rollbacks", str(recent_rollbacks))
        
        # Phase progress
        phase_progress = self._calculate_phase_progress(elapsed_hours)
        
        progress_bar = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        
        task = progress_bar.add_task(
            description=f"{self.controller.current_phase.value.title()} Phase",
            total=100
        )
        progress_bar.update(task, completed=phase_progress)
        
        # Combine displays
        from rich.columns import Columns
        
        status_panel = Panel(status_table, title="📊 Experiment Status")
        activity_panel = Panel(activity_table, title="⚡ Recent Activity")
        
        return Columns([status_panel, activity_panel], equal=True)
    
    def _calculate_phase_progress(self, elapsed_hours: float) -> float:
        """Calculate progress within current phase"""
        
        if self.controller.current_phase == ExperimentPhase.BASELINE:
            return min(100, (elapsed_hours / self.controller.BASELINE_HOURS) * 100)
        
        # Calculate cumulative hours for phase start
        baseline_hours = self.controller.BASELINE_HOURS
        phase_starts = {
            ExperimentPhase.INITIAL: baseline_hours,
            ExperimentPhase.MODERATE: baseline_hours + 48,
            ExperimentPhase.AGGRESSIVE: baseline_hours + 96, 
            ExperimentPhase.STABILIZATION: baseline_hours + 144
        }
        
        if self.controller.current_phase in phase_starts:
            phase_start = phase_starts[self.controller.current_phase]
            phase_duration = self.controller.PHASE_DURATION_HOURS.get(self.controller.current_phase, 24)
            phase_elapsed = elapsed_hours - phase_start
            
            return min(100, max(0, (phase_elapsed / phase_duration) * 100))
        
        return 100
    
    async def _generate_final_report(self):
        """Generate and display final experiment report"""
        
        console.print("\n[cyan]📋 Generating final experiment report...[/cyan]")
        
        try:
            report = self.controller.generate_experiment_report()
            
            # Display summary
            summary_text = f"""
[bold]Experiment Results Summary[/bold]

Duration: {report['experiment_summary']['start_time']} to {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
Total Data Points: {report['experiment_summary']['total_data_points']:,}
Channels Tested: {report['experiment_summary']['total_channels']}
Phases Completed: {', '.join(report['experiment_summary']['phases_completed'])}

Safety Events: {len(report['safety_events'])} rollbacks occurred
            """
            
            console.print(Panel(summary_text.strip(), title="📊 Final Results"))
            
            # Performance by group
            if report['performance_by_group']:
                console.print("\n[bold]📈 Performance by Group[/bold]")
                
                perf_table = Table(show_header=True, header_style="bold magenta")
                perf_table.add_column("Group")
                perf_table.add_column("Avg Revenue/Hour", justify="right") 
                perf_table.add_column("Flow Efficiency", justify="right")
                perf_table.add_column("Balance Health", justify="right")
                perf_table.add_column("Fee Changes", justify="right")
                
                for group, stats in report['performance_by_group'].items():
                    perf_table.add_row(
                        group.replace('_', ' ').title(),
                        f"{stats['avg_revenue_per_hour']:.0f} msat",
                        f"{stats['avg_flow_efficiency']:.2f}",
                        f"{stats['avg_balance_health']:.2f}",
                        str(stats['total_fee_changes'])
                    )
                
                console.print(perf_table)
            
            # Safety events
            if report['safety_events']:
                console.print("\n[bold yellow]⚠️ Safety Events[/bold yellow]")
                
                safety_table = Table(show_header=True)
                safety_table.add_column("Channel")
                safety_table.add_column("Group")
                safety_table.add_column("Rollbacks", justify="right")
                safety_table.add_column("Reasons")
                
                for event in report['safety_events']:
                    safety_table.add_row(
                        event['channel_id'][:16] + "...",
                        event['group'],
                        str(event['rollback_count']),
                        ", ".join(set(r.split(': ')[1] for r in event['rollback_reasons']))
                    )
                
                console.print(safety_table)
            
            # Save detailed report
            report_path = Path("experiment_data") / "final_report.json"
            import json
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            console.print(f"\n[green]📄 Detailed report saved to {report_path}[/green]")
            
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            console.print(f"[red]❌ Report generation failed: {e}[/red]")


@click.command()
@click.option('--lnd-manage-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--lnd-rest-url', default='http://localhost:8080', help='LND REST API URL')
@click.option('--config', type=click.Path(exists=True), help='Configuration file path')
@click.option('--duration', default=7, help='Experiment duration in days')
@click.option('--interval', default=30, help='Data collection interval in minutes')
@click.option('--dry-run', is_flag=True, help='Simulate experiment without actual fee changes')
@click.option('--resume', is_flag=True, help='Resume existing experiment')
def main(lnd_manage_url: str, lnd_rest_url: str, config: str, duration: int, interval: int, dry_run: bool, resume: bool):
    """Run Lightning Network fee optimization experiment"""
    
    if dry_run:
        console.print("[yellow]🔬 Running in DRY-RUN mode - no actual fee changes will be made[/yellow]")
    
    if resume:
        console.print("[cyan]🔄 Attempting to resume existing experiment...[/cyan]")
    
    try:
        runner = ExperimentRunner(lnd_manage_url, lnd_rest_url, config)
        asyncio.run(runner.run_experiment(duration, interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Experiment interrupted by user[/yellow]")
    except Exception as e:
        logger.exception("Fatal error in experiment")
        console.print(f"\n[red]Fatal error: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()