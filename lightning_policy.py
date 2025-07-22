#!/usr/bin/env python3
"""
Lightning Policy Manager - Improved charge-lnd with Advanced Inbound Fees

A modern, intelligent fee management system that combines the flexibility of charge-lnd
with advanced inbound fee strategies, machine learning, and automatic rollbacks.

Key improvements over charge-lnd:
- Advanced inbound fee strategies (not just discounts)
- Automatic performance tracking and rollbacks
- Revenue optimization focus
- Data-driven policy learning
- Integrated safety mechanisms
- SQLite database for historical analysis
"""

import asyncio
import logging
import sys
import json
from pathlib import Path
from datetime import datetime
import click
from tabulate import tabulate

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.policy.manager import PolicyManager
from src.policy.engine import create_sample_config


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('policy.log'),
            logging.StreamHandler(sys.stderr)
        ]
    )


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--lnd-manage-url', default='http://localhost:18081', help='LND Manage API URL')
@click.option('--lnd-rest-url', default='https://localhost:8080', help='LND REST API URL')
@click.option('--lnd-grpc-host', default='localhost:10009', help='LND gRPC endpoint (preferred)')
@click.option('--lnd-dir', default='~/.lnd', help='LND directory path')
@click.option('--prefer-grpc/--prefer-rest', default=True, help='Prefer gRPC over REST API (faster)')
@click.option('--config', '-c', type=click.Path(exists=True), help='Policy configuration file')
@click.pass_context
def cli(ctx, verbose, lnd_manage_url, lnd_rest_url, lnd_grpc_host, lnd_dir, prefer_grpc, config):
    """Lightning Policy Manager - Advanced fee management with inbound fees"""
    setup_logging(verbose)
    
    ctx.ensure_object(dict)
    
    # Only initialize manager if config is provided
    if config:
        ctx.obj['manager'] = PolicyManager(
            config_file=config,
            lnd_manage_url=lnd_manage_url,
            lnd_rest_url=lnd_rest_url,
            lnd_grpc_host=lnd_grpc_host,
            lnd_dir=lnd_dir,
            prefer_grpc=prefer_grpc
        )
    
    ctx.obj['verbose'] = verbose
    ctx.obj['lnd_manage_url'] = lnd_manage_url
    ctx.obj['lnd_rest_url'] = lnd_rest_url
    ctx.obj['lnd_grpc_host'] = lnd_grpc_host
    ctx.obj['prefer_grpc'] = prefer_grpc


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be changed without applying')
@click.option('--macaroon-path', help='Path to admin.macaroon file')
@click.option('--cert-path', help='Path to tls.cert file')
@click.pass_context
def apply(ctx, dry_run, macaroon_path, cert_path):
    """Apply policy-based fee changes to all channels"""
    manager = ctx.obj.get('manager')
    if not manager:
        click.echo("Error: Configuration file required. Use -c/--config option.")
        return
    
    async def _apply():
        if dry_run:
            print("DRY-RUN MODE: Showing policy recommendations without applying changes")
        else:
            protocol = "gRPC" if ctx.obj.get('prefer_grpc', True) else "REST"
            print(f"Applying policy-based fee changes via {protocol} API...")
        
        results = await manager.apply_policies(
            dry_run=dry_run,
            macaroon_path=macaroon_path,
            cert_path=cert_path
        )
        
        # Print summary
        print(f"\n=== POLICY APPLICATION RESULTS ===")
        print(f"Channels processed: {results['channels_processed']}")
        print(f"Policies applied: {results['policies_applied']}")
        print(f"Fee changes: {results['fee_changes']}")
        print(f"Errors: {len(results['errors'])}")
        
        if results['errors']:
            print(f"\n=== ERRORS ===")
            for error in results['errors'][:5]:  # Show first 5 errors
                print(f"• {error}")
            if len(results['errors']) > 5:
                print(f"... and {len(results['errors']) - 5} more errors")
        
        # Show policy matches
        if results['policy_matches']:
            print(f"\n=== POLICY MATCHES (Top 10) ===")
            matches_table = []
            for channel_id, policies in list(results['policy_matches'].items())[:10]:
                matches_table.append([
                    channel_id[:16] + "...",
                    ', '.join(policies)
                ])
            
            print(tabulate(matches_table, headers=["Channel", "Matched Policies"], tablefmt="grid"))
        
        # Show performance summary
        perf_summary = results['performance_summary']
        if perf_summary.get('policy_performance'):
            print(f"\n=== POLICY PERFORMANCE ===")
            perf_table = []
            for policy in perf_summary['policy_performance']:
                perf_table.append([
                    policy['name'],
                    policy['applied_count'],
                    policy['strategy'],
                    f"{policy['avg_revenue_impact']:.0f} msat"
                ])
            
            print(tabulate(perf_table, 
                         headers=["Policy", "Applied", "Strategy", "Avg Revenue Impact"], 
                         tablefmt="grid"))
    
    asyncio.run(_apply())


@cli.command()
@click.pass_context  
def status(ctx):
    """Show current policy manager status"""
    manager = ctx.obj.get('manager')
    if not manager:
        click.echo("Error: Configuration file required. Use -c/--config option.")
        return
    
    status_info = manager.get_policy_status()
    
    print("=== LIGHTNING POLICY MANAGER STATUS ===")
    print(f"Session ID: {status_info['session_id']}")
    print(f"Total Policy Rules: {status_info['total_rules']}")
    print(f"Active Rules: {status_info['active_rules']}")
    print(f"Channels with Recent Changes: {status_info['channels_with_changes']}")
    print(f"Rollback Candidates: {status_info['rollback_candidates']}")
    print(f"Recent Changes (24h): {status_info['recent_changes']}")
    
    # Show policy performance
    perf_report = status_info['performance_report']
    if perf_report.get('policy_performance'):
        print(f"\n=== ACTIVE POLICY PERFORMANCE ===")
        
        perf_table = []
        for policy in perf_report['policy_performance']:
            last_applied = policy.get('last_applied', 'Never')
            if last_applied != 'Never':
                last_applied = datetime.fromisoformat(last_applied).strftime('%m/%d %H:%M')
            
            perf_table.append([
                policy['name'],
                policy['applied_count'],
                policy['strategy'],
                f"{policy['avg_revenue_impact']:.0f}",
                last_applied
            ])
        
        print(tabulate(perf_table,
                     headers=["Policy", "Applied", "Strategy", "Avg Revenue", "Last Applied"],
                     tablefmt="grid"))


@cli.command()
@click.option('--execute', is_flag=True, help='Execute rollbacks (default is dry-run)')
@click.option('--macaroon-path', help='Path to admin.macaroon file')  
@click.option('--cert-path', help='Path to tls.cert file')
@click.pass_context
def rollback(ctx, execute, macaroon_path, cert_path):
    """Check for and execute automatic rollbacks of underperforming changes"""
    manager = ctx.obj['manager']
    
    async def _rollback():
        print("Checking rollback conditions...")
        
        rollback_info = await manager.check_rollback_conditions()
        
        print(f"Found {rollback_info['rollback_candidates']} channels requiring rollback")
        
        if rollback_info['rollback_candidates'] == 0:
            print("✓ No rollbacks needed")
            return
        
        # Show rollback candidates
        print(f"\n=== ROLLBACK CANDIDATES ===")
        rollback_table = []
        
        for action in rollback_info['actions']:
            rollback_table.append([
                action['channel_id'][:16] + "...",
                f"{action['revenue_decline']:.1%}",
                f"{action['threshold']:.1%}",
                f"{action['old_outbound']} → {action['new_outbound']}",
                f"{action['old_inbound']} → {action['new_inbound']}",
                ', '.join(action['policies'])
            ])
        
        print(tabulate(rollback_table,
                     headers=["Channel", "Decline", "Threshold", "Outbound Change", "Inbound Change", "Policies"],
                     tablefmt="grid"))
        
        if execute:
            print(f"\nExecuting {len(rollback_info['actions'])} rollbacks...")
            
            # Initialize LND connection
            from src.experiment.lnd_integration import LNDRestClient
            async with LNDRestClient(
                lnd_rest_url=manager.lnd_rest_url,
                cert_path=cert_path,
                macaroon_path=macaroon_path
            ) as lnd_rest:
                
                rollback_results = await manager.execute_rollbacks(
                    rollback_info['actions'], 
                    lnd_rest
                )
                
                print(f"✓ Rollbacks completed:")
                print(f"  Attempted: {rollback_results['rollbacks_attempted']}")
                print(f"  Successful: {rollback_results['rollbacks_successful']}")
                print(f"  Errors: {len(rollback_results['errors'])}")
                
                if rollback_results['errors']:
                    print(f"\n=== ROLLBACK ERRORS ===")
                    for error in rollback_results['errors']:
                        print(f"• {error}")
        else:
            print(f"\nDRY-RUN: Use --execute to actually perform rollbacks")
    
    asyncio.run(_rollback())


@cli.command()
@click.option('--output', '-o', help='Output file for report')
@click.option('--format', 'output_format', default='table', 
              type=click.Choice(['table', 'json', 'csv']), help='Output format')
@click.pass_context
def report(ctx, output, output_format):
    """Generate comprehensive policy performance report"""
    manager = ctx.obj['manager']
    
    status_info = manager.get_policy_status()
    perf_report = status_info['performance_report']
    
    if output_format == 'json':
        report_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'session_info': {
                'session_id': status_info['session_id'],
                'total_rules': status_info['total_rules'],
                'active_rules': status_info['active_rules'],
                'channels_with_changes': status_info['channels_with_changes']
            },
            'policy_performance': perf_report['policy_performance']
        }
        
        if output:
            with open(output, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"✓ JSON report saved to {output}")
        else:
            print(json.dumps(report_data, indent=2))
    
    elif output_format == 'table':
        print("=== POLICY PERFORMANCE REPORT ===")
        print(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Session: {status_info['session_id']}")
        print(f"Active Policies: {status_info['active_rules']}/{status_info['total_rules']}")
        
        if perf_report.get('policy_performance'):
            print(f"\n=== DETAILED POLICY PERFORMANCE ===")
            
            detailed_table = []
            for policy in perf_report['policy_performance']:
                last_applied = policy.get('last_applied', 'Never')
                if last_applied != 'Never':
                    last_applied = datetime.fromisoformat(last_applied).strftime('%Y-%m-%d %H:%M')
                
                detailed_table.append([
                    policy['name'],
                    policy['strategy'],
                    policy['applied_count'],
                    f"{policy['avg_revenue_impact']:+.0f} msat",
                    last_applied
                ])
            
            print(tabulate(detailed_table,
                         headers=["Policy Name", "Strategy", "Times Applied", "Avg Revenue Impact", "Last Applied"],
                         tablefmt="grid"))
        
        if output:
            # Save table format to file
            with open(output, 'w') as f:
                f.write("Policy Performance Report\n")
                f.write(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(tabulate(detailed_table,
                               headers=["Policy Name", "Strategy", "Times Applied", "Avg Revenue Impact", "Last Applied"],
                               tablefmt="grid"))
            print(f"✓ Report saved to {output}")


@cli.command()
@click.argument('output_file', type=click.Path())
@click.pass_context  
def generate_config(ctx, output_file):
    """Generate a sample configuration file with advanced features"""
    
    sample_config = create_sample_config()
    
    with open(output_file, 'w') as f:
        f.write(sample_config)
    
    print(f"✓ Sample configuration generated: {output_file}")
    print()
    print("This configuration demonstrates:")
    print("• Advanced inbound fee strategies")  
    print("• Balance-based and flow-based optimization")
    print("• Automatic rollback protection")
    print("• Revenue maximization policies")
    print("• Competitive fee adjustment")
    print("• Learning-enabled policies")
    print()
    print("Edit the configuration to match your node's requirements, then use:")
    print(f"  ./lightning_policy.py -c {output_file} apply --dry-run")


@cli.command()
@click.option('--watch', is_flag=True, help='Watch mode - apply policies every 10 minutes')
@click.option('--interval', default=10, help='Minutes between policy applications in watch mode')
@click.option('--macaroon-path', help='Path to admin.macaroon file')
@click.option('--cert-path', help='Path to tls.cert file')
@click.pass_context
def daemon(ctx, watch, interval, macaroon_path, cert_path):
    """Run policy manager in daemon mode with automatic rollbacks"""
    manager = ctx.obj['manager']
    
    if not watch:
        print("Use --watch to enable daemon mode")
        return
    
    async def _daemon():
        print(f"🤖 Starting policy daemon (interval: {interval} minutes)")
        print("Press Ctrl+C to stop")
        
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                print(f"\n--- Cycle {cycle_count} at {datetime.utcnow().strftime('%H:%M:%S')} ---")
                
                # Apply policies
                try:
                    results = await manager.apply_policies(
                        dry_run=False,
                        macaroon_path=macaroon_path,
                        cert_path=cert_path
                    )
                    
                    print(f"Applied {results['fee_changes']} fee changes")
                    
                    if results['errors']:
                        print(f"WARNING: {len(results['errors'])} errors occurred")
                
                except Exception as e:
                    print(f"❌ Policy application failed: {e}")
                
                # Check rollbacks
                try:
                    rollback_info = await manager.check_rollback_conditions()
                    
                    if rollback_info['rollback_candidates'] > 0:
                        print(f"🔙 Found {rollback_info['rollback_candidates']} rollback candidates")
                        
                        from src.experiment.lnd_integration import LNDRestClient
                        async with LNDRestClient(
                            lnd_rest_url=manager.lnd_rest_url,
                            cert_path=cert_path,
                            macaroon_path=macaroon_path
                        ) as lnd_rest:
                            
                            rollback_results = await manager.execute_rollbacks(
                                rollback_info['actions'],
                                lnd_rest
                            )
                            
                            print(f"Executed {rollback_results['rollbacks_successful']} rollbacks")
                
                except Exception as e:
                    print(f"❌ Rollback check failed: {e}")
                
                # Wait for next cycle
                print(f"💤 Sleeping for {interval} minutes...")
                await asyncio.sleep(interval * 60)
        
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped by user")
    
    asyncio.run(_daemon())


@cli.command()
@click.argument('channel_id')
@click.option('--verbose', is_flag=True, help='Show detailed policy evaluation')
@click.pass_context  
def test_channel(ctx, channel_id, verbose):
    """Test policy matching and fee calculation for a specific channel"""
    manager = ctx.obj['manager']
    
    async def _test():
        print(f"Testing policy evaluation for channel: {channel_id}")
        
        # Get channel data
        from src.api.client import LndManageClient
        async with LndManageClient(manager.lnd_manage_url) as lnd_manage:
            try:
                channel_details = await lnd_manage.get_channel_details(channel_id)
                enriched_data = await manager._enrich_channel_data(channel_details, lnd_manage)
                
                print(f"\n=== CHANNEL INFO ===")
                print(f"Capacity: {enriched_data['capacity']:,} sats")
                print(f"Balance Ratio: {enriched_data['local_balance_ratio']:.2%}")
                print(f"Activity Level: {enriched_data['activity_level']}")
                print(f"Current Outbound Fee: {enriched_data['current_outbound_fee']} ppm")
                print(f"Current Inbound Fee: {enriched_data['current_inbound_fee']} ppm")
                print(f"7d Flow: {enriched_data['flow_7d']:,} msat")
                
                # Test policy matching
                matching_rules = manager.policy_engine.match_channel(enriched_data)
                
                print(f"\n=== POLICY MATCHES ===")
                if not matching_rules:
                    print("No policies matched this channel")
                    return
                
                for i, rule in enumerate(matching_rules):
                    print(f"{i+1}. {rule.name} (priority: {rule.priority})")
                    print(f"   Strategy: {rule.policy.strategy.value}")
                    print(f"   Type: {rule.policy.policy_type.value}")
                    
                    if verbose:
                        print(f"   Applied {rule.applied_count} times")
                        if rule.last_applied:
                            print(f"   Last applied: {rule.last_applied.strftime('%Y-%m-%d %H:%M')}")
                
                # Calculate recommended fees
                outbound_fee, outbound_base, inbound_fee, inbound_base = \
                    manager.policy_engine.calculate_fees(enriched_data)
                
                print(f"\n=== RECOMMENDED FEES ===")
                print(f"Outbound Fee: {outbound_fee} ppm (base: {outbound_base} msat)")
                print(f"Inbound Fee: {inbound_fee:+} ppm (base: {inbound_base:+} msat)")
                
                # Show changes
                current_out = enriched_data['current_outbound_fee']
                current_in = enriched_data['current_inbound_fee']
                
                if outbound_fee != current_out or inbound_fee != current_in:
                    print(f"\n=== CHANGES ===")
                    if outbound_fee != current_out:
                        print(f"Outbound: {current_out} → {outbound_fee} ppm ({outbound_fee - current_out:+} ppm)")
                    if inbound_fee != current_in:
                        print(f"Inbound: {current_in:+} → {inbound_fee:+} ppm ({inbound_fee - current_in:+} ppm)")
                else:
                    print(f"\n✓ No fee changes recommended")
            
            except Exception as e:
                print(f"❌ Error testing channel: {e}")
    
    asyncio.run(_test())


if __name__ == "__main__":
    cli()