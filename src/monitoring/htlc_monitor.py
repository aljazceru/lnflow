"""HTLC Event Monitor - Track failed forwards and routing opportunities"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Callable, Protocol
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class GRPCClient(Protocol):
    """Protocol for gRPC client with HTLC support"""
    async def subscribe_htlc_events(self):
        """Subscribe to HTLC events"""
        ...


class HTLCEventType(Enum):
    """Types of HTLC events we track"""
    FORWARD = "forward"
    FORWARD_FAIL = "forward_fail"
    SETTLE = "settle"
    LINK_FAIL = "link_fail"


class FailureReason(Enum):
    """Reasons why HTLCs fail"""
    INSUFFICIENT_BALANCE = "insufficient_balance"
    FEE_INSUFFICIENT = "fee_insufficient"
    TEMPORARY_CHANNEL_FAILURE = "temporary_channel_failure"
    UNKNOWN_NEXT_PEER = "unknown_next_peer"
    INCORRECT_CLTV_EXPIRY = "incorrect_cltv_expiry"
    CHANNEL_DISABLED = "channel_disabled"
    UNKNOWN = "unknown"


@dataclass
class HTLCEvent:
    """Represents a single HTLC event"""
    timestamp: datetime
    event_type: HTLCEventType
    incoming_channel_id: Optional[str] = None
    outgoing_channel_id: Optional[str] = None
    incoming_htlc_id: Optional[int] = None
    outgoing_htlc_id: Optional[int] = None
    amount_msat: int = 0
    fee_msat: int = 0
    failure_reason: Optional[FailureReason] = None
    failure_source_index: Optional[int] = None

    def is_failure(self) -> bool:
        """Check if this event represents a failure"""
        return self.event_type in (HTLCEventType.FORWARD_FAIL, HTLCEventType.LINK_FAIL)

    def is_liquidity_failure(self) -> bool:
        """Check if failure was due to liquidity issues"""
        return self.failure_reason in (
            FailureReason.INSUFFICIENT_BALANCE,
            FailureReason.TEMPORARY_CHANNEL_FAILURE
        )


@dataclass
class ChannelFailureStats:
    """Statistics about failures on a specific channel"""
    channel_id: str
    total_forwards: int = 0
    successful_forwards: int = 0
    failed_forwards: int = 0
    liquidity_failures: int = 0
    fee_failures: int = 0
    total_missed_amount_msat: int = 0
    total_missed_fees_msat: int = 0
    recent_failures: deque = field(default_factory=lambda: deque(maxlen=100))
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_failure: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_forwards == 0:
            return 0.0
        return self.successful_forwards / self.total_forwards

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate"""
        return 1.0 - self.success_rate

    @property
    def missed_revenue_sats(self) -> float:
        """Get missed revenue in sats"""
        return self.total_missed_fees_msat / 1000


class HTLCMonitor:
    """Monitor HTLC events and detect missed routing opportunities"""

    def __init__(self,
                 grpc_client: Optional[GRPCClient] = None,
                 history_hours: int = 24,
                 min_failure_count: int = 3,
                 min_missed_sats: int = 100,
                 max_channels: int = 10000):
        """
        Initialize HTLC monitor

        Args:
            grpc_client: LND gRPC client for subscribing to events
            history_hours: How many hours of history to keep
            min_failure_count: Minimum failures to flag as opportunity
            min_missed_sats: Minimum missed sats to flag as opportunity
            max_channels: Maximum channels to track (prevents unbounded growth)
        """
        self.grpc_client = grpc_client
        self.history_hours = history_hours
        self.min_failure_count = min_failure_count
        self.min_missed_sats = min_missed_sats
        self.max_channels = max_channels

        # Event storage
        self.events: deque = deque(maxlen=10000)  # Last 10k events
        self.channel_stats: Dict[str, ChannelFailureStats] = {}

        # Monitoring state
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.callbacks: List[Callable[[HTLCEvent], None]] = []

        logger.info(f"HTLC Monitor initialized (history: {history_hours}h, "
                   f"min failures: {min_failure_count}, min sats: {min_missed_sats}, "
                   f"max channels: {max_channels})")

    def register_callback(self, callback: Callable[[HTLCEvent], None]):
        """Register a callback to be called on each HTLC event"""
        self.callbacks.append(callback)
        logger.debug(f"Registered callback: {callback.__name__}")

    async def __aenter__(self):
        """Async context manager entry - starts monitoring"""
        await self.start_monitoring()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - stops monitoring"""
        await self.stop_monitoring()
        return False

    async def start_monitoring(self):
        """Start monitoring HTLC events"""
        if self.monitoring:
            logger.warning("HTLC monitoring already running")
            return

        if not self.grpc_client:
            raise RuntimeError("No gRPC client provided - cannot monitor HTLCs")

        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Started HTLC event monitoring")

    async def stop_monitoring(self):
        """Stop monitoring HTLC events"""
        if not self.monitoring:
            return

        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped HTLC event monitoring")

    async def _monitor_loop(self):
        """Main monitoring loop - subscribes to HTLC events"""
        try:
            while self.monitoring:
                try:
                    # Subscribe to HTLC events from LND
                    logger.info("Subscribing to HTLC events...")
                    async for event_data in self._subscribe_htlc_events():
                        if not self.monitoring:
                            break

                        # Parse and store event
                        event = self._parse_htlc_event(event_data)
                        if event:
                            await self._process_event(event)

                except Exception as e:
                    if self.monitoring:
                        logger.error(f"Error in HTLC monitoring loop: {e}")
                        await asyncio.sleep(5)  # Wait before retrying
                    else:
                        break

        except asyncio.CancelledError:
            logger.info("HTLC monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in HTLC monitoring: {e}")
            self.monitoring = False

    async def _subscribe_htlc_events(self):
        """Subscribe to HTLC events from LND (streaming)"""
        # This would use the gRPC client's SubscribeHtlcEvents
        # For now, we'll use a placeholder that can be implemented
        if hasattr(self.grpc_client, 'subscribe_htlc_events'):
            async for event in self.grpc_client.subscribe_htlc_events():
                yield event
        else:
            # Fallback: poll forwarding history
            logger.warning("gRPC client doesn't support HTLC events, using polling fallback")
            while self.monitoring:
                await asyncio.sleep(60)  # Poll every minute
                # TODO: Implement forwarding history polling
                yield None

    def _parse_htlc_event(self, event_data: Dict) -> Optional[HTLCEvent]:
        """Parse raw HTLC event data into HTLCEvent object"""
        if not event_data:
            return None

        try:
            # Parse event type
            event_type_str = event_data.get('event_type', '').lower()
            event_type = HTLCEventType(event_type_str) if event_type_str else HTLCEventType.FORWARD

            # Parse failure reason if present
            failure_reason = None
            if 'failure_string' in event_data:
                failure_str = event_data['failure_string'].lower()
                if 'insufficient' in failure_str or 'balance' in failure_str:
                    failure_reason = FailureReason.INSUFFICIENT_BALANCE
                elif 'fee' in failure_str:
                    failure_reason = FailureReason.FEE_INSUFFICIENT
                elif 'temporary' in failure_str or 'channel_failure' in failure_str:
                    failure_reason = FailureReason.TEMPORARY_CHANNEL_FAILURE
                else:
                    failure_reason = FailureReason.UNKNOWN

            return HTLCEvent(
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                incoming_channel_id=event_data.get('incoming_channel_id'),
                outgoing_channel_id=event_data.get('outgoing_channel_id'),
                incoming_htlc_id=event_data.get('incoming_htlc_id'),
                outgoing_htlc_id=event_data.get('outgoing_htlc_id'),
                amount_msat=int(event_data.get('amount_msat', 0)),
                fee_msat=int(event_data.get('fee_msat', 0)),
                failure_reason=failure_reason,
                failure_source_index=event_data.get('failure_source_index')
            )

        except Exception as e:
            logger.error(f"Failed to parse HTLC event: {e}")
            return None

    async def _process_event(self, event: HTLCEvent):
        """Process a single HTLC event"""
        # Store event
        self.events.append(event)

        # Update channel statistics
        if event.outgoing_channel_id:
            channel_id = event.outgoing_channel_id

            if channel_id not in self.channel_stats:
                # Prevent unbounded memory growth
                if len(self.channel_stats) >= self.max_channels:
                    # Remove least active channel
                    oldest_channel = min(
                        self.channel_stats.items(),
                        key=lambda x: x[1].last_failure or x[1].first_seen
                    )
                    logger.info(f"Removing inactive channel {oldest_channel[0]} (at max_channels limit)")
                    del self.channel_stats[oldest_channel[0]]

                self.channel_stats[channel_id] = ChannelFailureStats(channel_id=channel_id)

            stats = self.channel_stats[channel_id]
            stats.total_forwards += 1

            if event.is_failure():
                stats.failed_forwards += 1
                stats.recent_failures.append(event)
                stats.last_failure = event.timestamp
                stats.total_missed_amount_msat += event.amount_msat
                stats.total_missed_fees_msat += event.fee_msat

                if event.is_liquidity_failure():
                    stats.liquidity_failures += 1
                elif event.failure_reason == FailureReason.FEE_INSUFFICIENT:
                    stats.fee_failures += 1
            else:
                stats.successful_forwards += 1

        # Trigger callbacks
        for callback in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in HTLC event callback: {e}")

        # Log significant failures
        if event.is_liquidity_failure():
            logger.warning(
                f"Liquidity failure on channel {event.outgoing_channel_id}: "
                f"{event.amount_msat/1000:.0f} sats, potential fee: {event.fee_msat/1000:.2f} sats"
            )

    def get_channel_stats(self, channel_id: str) -> Optional[ChannelFailureStats]:
        """Get failure statistics for a specific channel"""
        return self.channel_stats.get(channel_id)

    def get_top_missed_opportunities(self, limit: int = 10) -> List[ChannelFailureStats]:
        """Get channels with most missed opportunities"""
        # Filter channels with significant failures
        opportunities = [
            stats for stats in self.channel_stats.values()
            if (stats.failed_forwards >= self.min_failure_count and
                stats.missed_revenue_sats >= self.min_missed_sats)
        ]

        # Sort by missed revenue
        opportunities.sort(key=lambda x: x.total_missed_fees_msat, reverse=True)

        return opportunities[:limit]

    def get_liquidity_constrained_channels(self) -> List[ChannelFailureStats]:
        """Get channels that failed primarily due to liquidity issues"""
        return [
            stats for stats in self.channel_stats.values()
            if (stats.liquidity_failures >= self.min_failure_count and
                stats.liquidity_failures / max(stats.failed_forwards, 1) > 0.5)
        ]

    def get_fee_constrained_channels(self) -> List[ChannelFailureStats]:
        """Get channels that failed primarily due to high fees"""
        return [
            stats for stats in self.channel_stats.values()
            if (stats.fee_failures >= self.min_failure_count and
                stats.fee_failures / max(stats.failed_forwards, 1) > 0.3)
        ]

    def get_summary_stats(self) -> Dict:
        """Get overall monitoring statistics"""
        total_events = len(self.events)
        total_failures = sum(1 for e in self.events if e.is_failure())
        total_liquidity_failures = sum(1 for e in self.events if e.is_liquidity_failure())

        total_missed_revenue = sum(
            stats.total_missed_fees_msat for stats in self.channel_stats.values()
        ) / 1000  # Convert to sats

        return {
            'monitoring_active': self.monitoring,
            'total_events': total_events,
            'total_failures': total_failures,
            'liquidity_failures': total_liquidity_failures,
            'channels_tracked': len(self.channel_stats),
            'total_missed_revenue_sats': total_missed_revenue,
            'history_hours': self.history_hours,
            'opportunities_found': len(self.get_top_missed_opportunities())
        }

    def cleanup_old_data(self):
        """Remove data older than history_hours"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.history_hours)

        # Clean old events
        while self.events and self.events[0].timestamp < cutoff:
            self.events.popleft()

        # Clean old channel stats (inactive channels)
        channels_removed = 0
        for channel_id in list(self.channel_stats.keys()):
            stats = self.channel_stats[channel_id]
            # Remove if no activity in the history window
            if stats.last_failure and stats.last_failure < cutoff:
                del self.channel_stats[channel_id]
                channels_removed += 1

        if channels_removed > 0:
            logger.info(f"Cleaned up {channels_removed} inactive channels (cutoff: {cutoff})")
        logger.debug(f"Active channels: {len(self.channel_stats)}")
