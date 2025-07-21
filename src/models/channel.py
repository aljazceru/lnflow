"""Channel data models based on actual API structure"""

from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from pydantic import BaseModel, Field


class ChannelBalance(BaseModel):
    """Channel balance information"""
    local_balance_sat: int = Field(default=0, alias="localBalanceSat")
    local_available_sat: int = Field(default=0, alias="localAvailableSat")
    local_reserve_sat: int = Field(default=0, alias="localReserveSat")
    remote_balance_sat: int = Field(default=0, alias="remoteBalanceSat")
    remote_available_sat: int = Field(default=0, alias="remoteAvailableSat")
    remote_reserve_sat: int = Field(default=0, alias="remoteReserveSat")
    
    @property
    def total_capacity(self) -> int:
        return self.local_balance_sat + self.remote_balance_sat
    
    @property
    def local_balance_ratio(self) -> float:
        if self.total_capacity == 0:
            return 0.0
        return self.local_balance_sat / self.total_capacity


class ChannelStatus(BaseModel):
    """Channel status information"""
    active: bool = True
    closed: bool = False
    open_closed: str = Field(default="OPEN", alias="openClosed")
    private: bool = False


class ChannelPolicy(BaseModel):
    """Channel fee policy"""
    fee_rate_ppm: int = Field(default=0, alias="feeRatePpm")
    base_fee_msat: str = Field(default="0", alias="baseFeeMilliSat")
    inbound_fee_rate_ppm: int = Field(default=0, alias="inboundFeeRatePpm")
    inbound_base_fee_msat: str = Field(default="0", alias="inboundBaseFeeMilliSat")
    enabled: bool = True
    time_lock_delta: int = Field(default=40, alias="timeLockDelta")
    min_htlc_msat: str = Field(default="1000", alias="minHtlcMilliSat")
    max_htlc_msat: str = Field(default="990000000", alias="maxHtlcMilliSat")
    
    @property
    def base_fee_msat_int(self) -> int:
        return int(self.base_fee_msat)


class ChannelPolicies(BaseModel):
    """Local and remote channel policies"""
    local: Optional[ChannelPolicy] = None
    remote: Optional[ChannelPolicy] = None


class FlowReport(BaseModel):
    """Channel flow metrics based on actual API structure"""
    forwarded_sent_msat: int = Field(default=0, alias="forwardedSentMilliSat")
    forwarded_received_msat: int = Field(default=0, alias="forwardedReceivedMilliSat")
    forwarding_fees_received_msat: int = Field(default=0, alias="forwardingFeesReceivedMilliSat")
    rebalance_sent_msat: int = Field(default=0, alias="rebalanceSentMilliSat")
    rebalance_fees_sent_msat: int = Field(default=0, alias="rebalanceFeesSentMilliSat")
    rebalance_received_msat: int = Field(default=0, alias="rebalanceReceivedMilliSat")
    rebalance_support_sent_msat: int = Field(default=0, alias="rebalanceSupportSentMilliSat")
    rebalance_support_fees_sent_msat: int = Field(default=0, alias="rebalanceSupportFeesSentMilliSat")
    rebalance_support_received_msat: int = Field(default=0, alias="rebalanceSupportReceivedMilliSat")
    received_via_payments_msat: int = Field(default=0, alias="receivedViaPaymentsMilliSat")
    total_sent_msat: int = Field(default=0, alias="totalSentMilliSat")
    total_received_msat: int = Field(default=0, alias="totalReceivedMilliSat")
    
    @property
    def total_flow(self) -> int:
        return self.total_sent_msat + self.total_received_msat
    
    @property
    def net_flow(self) -> int:
        return self.total_received_msat - self.total_sent_msat
    
    @property
    def total_flow_sats(self) -> float:
        return self.total_flow / 1000


class FeeReport(BaseModel):
    """Channel fee earnings"""
    earned_msat: int = Field(default=0, alias="earnedMilliSat")
    sourced_msat: int = Field(default=0, alias="sourcedMilliSat")
    
    @property
    def total_fees(self) -> int:
        return self.earned_msat + self.sourced_msat
    
    @property
    def total_fees_sats(self) -> float:
        return self.total_fees / 1000


class RebalanceReport(BaseModel):
    """Channel rebalancing information"""
    source_costs_msat: int = Field(default=0, alias="sourceCostsMilliSat")
    source_amount_msat: int = Field(default=0, alias="sourceAmountMilliSat")
    target_costs_msat: int = Field(default=0, alias="targetCostsMilliSat")
    target_amount_msat: int = Field(default=0, alias="targetAmountMilliSat")
    support_as_source_amount_msat: int = Field(default=0, alias="supportAsSourceAmountMilliSat")
    support_as_target_amount_msat: int = Field(default=0, alias="supportAsTargetAmountMilliSat")
    
    @property
    def net_rebalance_cost(self) -> int:
        return self.source_costs_msat + self.target_costs_msat
    
    @property
    def net_rebalance_amount(self) -> int:
        return self.target_amount_msat - self.source_amount_msat


class OnChainCosts(BaseModel):
    """On-chain costs for channel operations"""
    open_costs_sat: str = Field(default="0", alias="openCostsSat")
    close_costs_sat: str = Field(default="0", alias="closeCostsSat")
    sweep_costs_sat: str = Field(default="0", alias="sweepCostsSat")
    
    @property
    def total_costs_sat(self) -> int:
        return int(self.open_costs_sat) + int(self.close_costs_sat) + int(self.sweep_costs_sat)


class ChannelRating(BaseModel):
    """Channel rating information"""
    rating: int = -1
    message: str = ""
    descriptions: Dict[str, Union[str, float]] = Field(default_factory=dict)


class ChannelWarnings(BaseModel):
    """Channel warnings"""
    warnings: List[str] = Field(default_factory=list)


class Channel(BaseModel):
    """Complete channel data based on actual API structure"""
    channel_id_short: str = Field(alias="channelIdShort")
    channel_id_compact: str = Field(alias="channelIdCompact")
    channel_id_compact_lnd: str = Field(alias="channelIdCompactLnd")
    channel_point: str = Field(alias="channelPoint")
    open_height: int = Field(alias="openHeight")
    remote_pubkey: str = Field(alias="remotePubkey")
    remote_alias: Optional[str] = Field(default=None, alias="remoteAlias")
    capacity_sat: str = Field(alias="capacitySat")
    total_sent_sat: str = Field(alias="totalSentSat")
    total_received_sat: str = Field(alias="totalReceivedSat")
    status: ChannelStatus
    open_initiator: str = Field(alias="openInitiator")
    balance: Optional[ChannelBalance] = None
    on_chain_costs: Optional[OnChainCosts] = Field(default=None, alias="onChainCosts")
    policies: Optional[ChannelPolicies] = None
    fee_report: Optional[FeeReport] = Field(default=None, alias="feeReport")
    flow_report: Optional[FlowReport] = Field(default=None, alias="flowReport")
    rebalance_report: Optional[RebalanceReport] = Field(default=None, alias="rebalanceReport")
    num_updates: int = Field(default=0, alias="numUpdates")
    min_htlc_constraint_msat: str = Field(default="1", alias="minHtlcConstraintMsat")
    warnings: List[str] = Field(default_factory=list)
    rating: Optional[ChannelRating] = None
    
    # Additional computed fields
    timestamp: Optional[datetime] = None
    
    @property
    def capacity_sat_int(self) -> int:
        return int(self.capacity_sat)
    
    @property
    def is_active(self) -> bool:
        """Check if channel is active (has recent flow)"""
        return self.status.active and not self.status.closed
    
    @property
    def local_balance_ratio(self) -> float:
        """Get local balance ratio"""
        if not self.balance:
            return 0.5
        return self.balance.local_balance_ratio
    
    @property
    def total_flow_sats(self) -> float:
        """Total flow in sats"""
        if not self.flow_report:
            return 0.0
        return self.flow_report.total_flow_sats
    
    @property
    def net_flow_sats(self) -> float:
        """Net flow in sats"""
        if not self.flow_report:
            return 0.0
        return self.flow_report.net_flow / 1000
    
    @property
    def total_fees_sats(self) -> float:
        """Total fees earned in sats"""
        if not self.fee_report:
            return 0.0
        return self.fee_report.total_fees_sats
    
    @property
    def current_fee_rate(self) -> int:
        """Current local fee rate in ppm"""
        if not self.policies or not self.policies.local:
            return 0
        return self.policies.local.fee_rate_ppm
    
    class Config:
        populate_by_name = True