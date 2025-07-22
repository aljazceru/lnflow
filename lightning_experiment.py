#!/usr/bin/env python3
"""Lightning Fee Optimization Experiment - CLI Tool"""

import asyncio
import logging
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import click
from tabulate import tabulate
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.experiment.controller import ExperimentController, ExperimentPhase, ParameterSet, ChannelSegment
from src.experiment.lnd_integration import LNDRestClient, ExperimentLNDIntegration
from src.utils.config import Config


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('experiment.log'),
            logging.StreamHandler(sys.stderr)
        ]
    )


class CLIExperimentRunner:
    """Simple CLI experiment runner"""
    
    def __init__(self, lnd_manage_url: str, lnd_rest_url: str, config_path: str = None):
        self.config = Config.load(config_path) if config_path else Config()
        self.controller = ExperimentController(
            config=self.config,
            lnd_manage_url=lnd_manage_url,
            lnd_rest_url=lnd_rest_url
        )
        
        # LND integration for actual fee changes
        self.lnd_integration = None
        self.running = False
    
    async def initialize_lnd_integration(self, macaroon_path: str = None, cert_path: str = None):
        """Initialize LND REST client for fee changes"""
        try:
            lnd_client = LNDRestClient(
                lnd_rest_url=self.controller.lnd_rest_url,
                cert_path=cert_path,
                macaroon_path=macaroon_path
            )
            
            async with lnd_client as client:
                info = await client.get_node_info()
                print(f"✓ Connected to LND node: {info.get('alias', 'Unknown')} ({info.get('identity_pubkey', '')[:16]}...)")
                
            self.lnd_integration = ExperimentLNDIntegration(lnd_client)
            return True
            
        except Exception as e:
            print(f"✗ Failed to connect to LND: {e}")
            return False
    
    def print_experiment_setup(self):
        """Print experiment setup information"""
        segment_counts = self.controller._get_segment_counts()
        
        print("\n=== EXPERIMENT SETUP ===")
        print(f"Start Time: {self.controller.experiment_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Total Channels: {len(self.controller.experiment_channels)}")
        print()
        
        print("Channel Segments:")
        for segment, count in segment_counts.items():
            print(f"  {segment.replace('_', ' ').title()}: {count} channels")
        print()
        
        print("Safety Limits:")
        print(f"  Max fee increase: {self.controller.MAX_FEE_INCREASE_PCT:.0%}")
        print(f"  Max fee decrease: {self.controller.MAX_FEE_DECREASE_PCT:.0%}")
        print(f"  Max daily changes: {self.controller.MAX_DAILY_CHANGES} per channel")
        print(f"  Auto rollback: {self.controller.ROLLBACK_REVENUE_THRESHOLD:.0%} revenue drop or {self.controller.ROLLBACK_FLOW_THRESHOLD:.0%} flow reduction")
        print()
    
    def print_status(self):
        """Print current experiment status"""
        current_time = datetime.utcnow()
        if self.controller.experiment_start:
            elapsed_hours = (current_time - self.controller.experiment_start).total_seconds() / 3600
        else:
            elapsed_hours = 0
        
        # Recent activity count
        recent_changes = 0
        recent_rollbacks = 0
        
        for exp_channel in self.controller.experiment_channels.values():
            recent_changes += len([
                change for change in exp_channel.change_history
                if (current_time - datetime.fromisoformat(change['timestamp'])).total_seconds() < 24 * 3600
            ])
            
            recent_rollbacks += len([
                change for change in exp_channel.change_history
                if (current_time - datetime.fromisoformat(change['timestamp'])).total_seconds() < 24 * 3600
                and 'ROLLBACK' in change['reason']
            ])
        
        print(f"\n=== EXPERIMENT STATUS ===")
        print(f"Current Phase: {self.controller.current_phase.value.title()}")
        print(f"Elapsed Hours: {elapsed_hours:.1f}")
        print(f"Data Points Collected: {len(self.controller.data_points)}")
        print(f"Last Update: {current_time.strftime('%H:%M:%S UTC')}")
        print()
        print(f"Recent Activity (24h):")
        print(f"  Fee Changes: {recent_changes}")
        print(f"  Rollbacks: {recent_rollbacks}")
        print()
    
    def print_channel_details(self, group_filter: str = None):
        """Print detailed channel information"""
        
        if group_filter:
            try:
                segment_enum = ChannelSegment(segment_filter)
                channels = {k: v for k, v in self.controller.experiment_channels.items() if v.group == group_enum}
                title = f"=== {group_filter.upper()} GROUP CHANNELS ==="
            except ValueError:
                print(f"Invalid group: {group_filter}. Valid groups: control, treatment_a, treatment_b, treatment_c")
                return
        else:
            channels = self.controller.experiment_channels
            title = "=== ALL EXPERIMENT CHANNELS ==="
        
        print(f"\n{title}")
        
        # Create table data
        table_data = []
        headers = ["Channel ID", "Group", "Tier", "Activity", "Current Fee", "Changes", "Status"]
        
        for channel_id, exp_channel in channels.items():
            status = "Active"
            
            # Check for recent rollbacks
            recent_rollbacks = [
                change for change in exp_channel.change_history
                if 'ROLLBACK' in change['reason'] and
                   (datetime.utcnow() - datetime.fromisoformat(change['timestamp'])).total_seconds() < 24 * 3600
            ]
            
            if recent_rollbacks:
                status = "Rolled Back"
            
            table_data.append([
                channel_id[:16] + "...",
                exp_channel.segment.value,
                exp_channel.capacity_tier,
                exp_channel.activity_level,
                f"{exp_channel.current_fee_rate} ppm",
                len(exp_channel.change_history),
                status
            ])
        
        if table_data:
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
        else:
            print("No channels found.")
        print()
    
    def print_performance_summary(self):
        """Print performance summary by parameter set"""
        # Get performance data from database
        if not self.controller.experiment_id:
            print("No experiment data available.")
            return
            
        performance_data = {}
        
        # Get performance by parameter set
        for param_set in ParameterSet:
            perf = self.controller.db.get_parameter_set_performance(
                self.controller.experiment_id, param_set.value
            )
            if perf:
                performance_data[param_set.value] = perf
        
        print("\n=== PERFORMANCE SUMMARY ===")
        
        # Create summary table
        table_data = []
        headers = ["Parameter Set", "Channels", "Avg Revenue", "Flow Efficiency", "Balance Health", "Period"]
        
        for param_set, perf in performance_data.items():
            if perf.get('channels', 0) > 0:
                start_time = perf.get('start_time', '')
                end_time = perf.get('end_time', '')
                
                if start_time and end_time:
                    period = f"{start_time[:10]} to {end_time[:10]}"
                else:
                    current_set = getattr(self.controller, 'current_parameter_set', ParameterSet.BASELINE)
                    period = "In Progress" if param_set == current_set.value else "Not Started"
                
                table_data.append([
                    param_set.replace('_', ' ').title(),
                    perf.get('channels', 0),
                    f"{perf.get('avg_revenue', 0):.0f} msat",
                    f"{perf.get('avg_flow_efficiency', 0):.3f}",
                    f"{perf.get('avg_balance_health', 0):.3f}",
                    period
                ])
        
        if table_data:
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
        else:
            print("No performance data available yet.")
        print()
    
    def print_recent_changes(self, hours: int = 24):
        """Print recent fee changes"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        recent_changes = []
        
        for channel_id, exp_channel in self.controller.experiment_channels.items():
            for change in exp_channel.change_history:
                change_time = datetime.fromisoformat(change['timestamp'])
                if change_time > cutoff_time:
                    recent_changes.append({
                        'timestamp': change_time,
                        'channel_id': channel_id,
                        'segment': exp_channel.segment.value,
                        **change
                    })
        
        # Sort by timestamp
        recent_changes.sort(key=lambda x: x['timestamp'], reverse=True)
        
        print(f"\n=== RECENT CHANGES (Last {hours}h) ===")
        
        if not recent_changes:
            print("No recent changes.")
            return
        
        table_data = []
        headers = ["Time", "Channel", "Group", "Old Fee", "New Fee", "Reason"]
        
        for change in recent_changes[:20]:  # Show last 20 changes
            is_rollback = 'ROLLBACK' in change['reason']
            old_fee = change.get('old_fee', 'N/A')
            new_fee = change.get('new_fee', 'N/A')
            reason = change['reason'][:50] + "..." if len(change['reason']) > 50 else change['reason']
            
            status_indicator = "ROLLBACK" if is_rollback else "UPDATE"
            
            table_data.append([
                change['timestamp'].strftime('%H:%M:%S'),
                change['channel_id'][:12] + "...",
                change['group'],
                f"{old_fee} ppm",
                f"{new_fee} ppm {status_indicator}",
                reason
            ])
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print()
    
    async def run_single_cycle(self, dry_run: bool = False):
        """Run a single experiment cycle"""
        if not dry_run and not self.lnd_integration:
            print("✗ LND integration not initialized. Use --dry-run for simulation.")
            return False
        
        try:
            print(f"Running experiment cycle...")
            
            # Monkey patch the fee application if dry run
            if dry_run:
                original_apply = self.controller._apply_channel_fee_change
                async def mock_apply(channel_id, new_fees):
                    print(f"  [DRY-RUN] Would update {channel_id}: {new_fees}")
                    return True
                self.controller._apply_channel_fee_change = mock_apply
            
            success = await self.controller.run_experiment_cycle()
            
            if success:
                print("✓ Cycle completed successfully")
                return True
            else:
                print("✓ Experiment completed")
                return False
                
        except Exception as e:
            print(f"✗ Cycle failed: {e}")
            return False
    
    def save_report(self, filepath: str = None):
        """Save experiment report to file"""
        if not filepath:
            filepath = f"experiment_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            report = self.controller.generate_experiment_report()
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            print(f"✓ Report saved to {filepath}")
            
            # Print summary
            summary = report.get('experiment_summary', {})
            performance = report.get('performance_by_parameter_set', {})
            safety = report.get('safety_events', [])
            
            print(f"\nReport Summary:")
            print(f"  Data Points: {summary.get('total_data_points', 0):,}")
            print(f"  Channels: {summary.get('total_channels', 0)}")
            print(f"  Safety Events: {len(safety)}")
            print()
            
            return filepath
            
        except Exception as e:
            print(f"✗ Failed to save report: {e}")
            return None


# CLI Commands
@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--lnd-manage-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--lnd-rest-url', default='https://localhost:8080', help='LND REST API URL')
@click.option('--config', type=click.Path(exists=True), help='Configuration file path')
@click.pass_context
def cli(ctx, verbose, lnd_manage_url, lnd_rest_url, config):
    """Lightning Network Fee Optimization Experiment Tool"""
    setup_logging(verbose)
    
    ctx.ensure_object(dict)
    ctx.obj['runner'] = CLIExperimentRunner(lnd_manage_url, lnd_rest_url, config)
    ctx.obj['verbose'] = verbose


@cli.command()
@click.option('--duration', default=7, help='Experiment duration in days')
@click.option('--macaroon-path', help='Path to admin.macaroon file')
@click.option('--cert-path', help='Path to tls.cert file')
@click.option('--dry-run', is_flag=True, help='Simulate without actual fee changes')
@click.pass_context
def init(ctx, duration, macaroon_path, cert_path, dry_run):
    """Initialize new experiment"""
    runner = ctx.obj['runner']
    
    async def _init():
        print("🔬 Initializing Lightning Fee Optimization Experiment")
        print(f"Duration: {duration} days")
        
        if not dry_run:
            print("📡 Connecting to LND...")
            success = await runner.initialize_lnd_integration(macaroon_path, cert_path)
            if not success:
                print("Use --dry-run to simulate without LND connection")
                return
        else:
            print("Running in DRY-RUN mode (no actual fee changes)")
        
        print("Analyzing channels and assigning segments...")
        success = await runner.controller.initialize_experiment(duration)
        
        if success:
            print("✓ Experiment initialized successfully")
            runner.print_experiment_setup()
        else:
            print("✗ Failed to initialize experiment")
    
    asyncio.run(_init())


@cli.command()
@click.pass_context
def status(ctx):
    """Show experiment status"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    runner.print_status()


@cli.command()
@click.option('--group', help='Filter by group: control, treatment_a, treatment_b, treatment_c')
@click.pass_context
def channels(ctx, group):
    """Show channel details"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    runner.print_channel_details(group)


@cli.command()
@click.option('--hours', default=24, help='Show changes from last N hours')
@click.pass_context
def changes(ctx, hours):
    """Show recent fee changes"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    runner.print_recent_changes(hours)


@cli.command()
@click.pass_context
def performance(ctx):
    """Show performance summary by parameter set"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    runner.print_performance_summary()


@cli.command()
@click.option('--dry-run', is_flag=True, help='Simulate cycle without actual changes')
@click.option('--macaroon-path', help='Path to admin.macaroon file')
@click.option('--cert-path', help='Path to tls.cert file')
@click.pass_context
def cycle(ctx, dry_run, macaroon_path, cert_path):
    """Run single experiment cycle"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    async def _cycle():
        if not dry_run and not runner.lnd_integration:
            success = await runner.initialize_lnd_integration(macaroon_path, cert_path)
            if not success:
                print("Use --dry-run to simulate")
                return
        
        await runner.run_single_cycle(dry_run)
    
    asyncio.run(_cycle())


@cli.command()
@click.option('--interval', default=30, help='Collection interval in minutes')
@click.option('--max-cycles', default=None, type=int, help='Maximum cycles to run')
@click.option('--dry-run', is_flag=True, help='Simulate without actual changes')
@click.option('--macaroon-path', help='Path to admin.macaroon file')
@click.option('--cert-path', help='Path to tls.cert file')
@click.pass_context
def run(ctx, interval, max_cycles, dry_run, macaroon_path, cert_path):
    """Run experiment continuously"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment running. Use 'init' to start.")
        return
    
    async def _run():
        if not dry_run and not runner.lnd_integration:
            success = await runner.initialize_lnd_integration(macaroon_path, cert_path)
            if not success:
                print("Use --dry-run to simulate")
                return
        
        print(f"Starting experiment run (interval: {interval} minutes)")
        if max_cycles:
            print(f"Will run maximum {max_cycles} cycles")
        print("Press Ctrl+C to stop")
        print()
        
        cycle_count = 0
        runner.running = True
        
        try:
            while runner.running:
                cycle_count += 1
                print(f"--- Cycle {cycle_count} ---")
                
                should_continue = await runner.run_single_cycle(dry_run)
                
                if not should_continue:
                    print("Experiment completed!")
                    break
                
                if max_cycles and cycle_count >= max_cycles:
                    print(f"Reached maximum cycles ({max_cycles})")
                    break
                
                print(f"⏳ Waiting {interval} minutes until next cycle...")
                
                # Wait with ability to interrupt
                for i in range(interval * 60):
                    if not runner.running:
                        break
                    await asyncio.sleep(1)
                    
        except KeyboardInterrupt:
            print("\nExperiment stopped by user")
        
        print("Generating final report...")
        runner.save_report()
    
    asyncio.run(_run())


@cli.command()
@click.option('--output', '-o', help='Output file path')
@click.pass_context
def report(ctx, output):
    """Generate experiment report"""
    runner = ctx.obj['runner']
    
    if not runner.controller.experiment_start:
        print("No experiment data available. Use 'init' to start.")
        return
    
    filepath = runner.save_report(output)
    
    if filepath:
        runner.print_performance_summary()


@cli.command()
@click.option('--backup', is_flag=True, help='Backup current experiment data')
@click.pass_context
def reset(ctx, backup):
    """Reset experiment (clear all data)"""
    runner = ctx.obj['runner']
    
    if backup:
        print("📦 Backing up current experiment...")
        runner.save_report(f"experiment_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    
    # Clear experiment data
    runner.controller.experiment_channels.clear()
    runner.controller.data_points.clear()
    runner.controller.experiment_start = None
    runner.controller.current_phase = ExperimentPhase.BASELINE
    
    print("Experiment reset. Use 'init' to start new experiment.")


if __name__ == "__main__":
    cli()