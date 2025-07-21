"""SQLite database for Lightning fee optimization experiment data"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ExperimentDatabase:
    """SQLite database for experiment data storage and analysis"""
    
    def __init__(self, db_path: str = "experiment_data/experiment.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database schema"""
        with self._get_connection() as conn:
            # Experiment metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_days INTEGER,
                    status TEXT DEFAULT 'running',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Channel configuration table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    experiment_id INTEGER NOT NULL,
                    segment TEXT NOT NULL,
                    capacity_sat INTEGER NOT NULL,
                    monthly_flow_msat INTEGER NOT NULL,
                    peer_pubkey TEXT,
                    baseline_fee_rate INTEGER NOT NULL,
                    baseline_inbound_fee INTEGER DEFAULT 0,
                    current_fee_rate INTEGER NOT NULL,
                    current_inbound_fee INTEGER DEFAULT 0,
                    original_metrics TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                )
            """)
            
            # Time series data points
            conn.execute("""
                CREATE TABLE IF NOT EXISTS data_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    experiment_id INTEGER NOT NULL,
                    experiment_hour INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    segment TEXT NOT NULL,
                    parameter_set TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    
                    -- Fee policy
                    outbound_fee_rate INTEGER NOT NULL,
                    inbound_fee_rate INTEGER NOT NULL,
                    base_fee_msat INTEGER NOT NULL,
                    
                    -- Balance metrics
                    local_balance_sat INTEGER NOT NULL,
                    remote_balance_sat INTEGER NOT NULL,
                    local_balance_ratio REAL NOT NULL,
                    
                    -- Flow metrics
                    forwarded_in_msat INTEGER DEFAULT 0,
                    forwarded_out_msat INTEGER DEFAULT 0,
                    fee_earned_msat INTEGER DEFAULT 0,
                    routing_events INTEGER DEFAULT 0,
                    
                    -- Network context
                    peer_fee_rates TEXT,
                    alternative_routes INTEGER DEFAULT 0,
                    
                    -- Derived metrics
                    revenue_rate_per_hour REAL DEFAULT 0.0,
                    flow_efficiency REAL DEFAULT 0.0,
                    balance_health_score REAL DEFAULT 0.0,
                    
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id),
                    FOREIGN KEY (channel_id) REFERENCES channels (channel_id)
                )
            """)
            
            # Fee changes history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fee_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    experiment_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    parameter_set TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    
                    old_fee INTEGER NOT NULL,
                    new_fee INTEGER NOT NULL,
                    old_inbound INTEGER NOT NULL,
                    new_inbound INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    success BOOLEAN DEFAULT TRUE,
                    
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id),
                    FOREIGN KEY (channel_id) REFERENCES channels (channel_id)
                )
            """)
            
            # Performance summary by parameter set
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parameter_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id INTEGER NOT NULL,
                    parameter_set TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    
                    total_revenue_msat INTEGER DEFAULT 0,
                    total_flow_msat INTEGER DEFAULT 0,
                    active_channels INTEGER DEFAULT 0,
                    fee_changes INTEGER DEFAULT 0,
                    rollbacks INTEGER DEFAULT 0,
                    
                    avg_fee_rate REAL DEFAULT 0.0,
                    avg_balance_health REAL DEFAULT 0.0,
                    avg_flow_efficiency REAL DEFAULT 0.0,
                    
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                )
            """)
            
            # Create useful indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_data_points_channel_time ON data_points(channel_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_data_points_parameter_set ON data_points(parameter_set, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fee_changes_channel_time ON fee_changes(channel_id, timestamp)")
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def create_experiment(self, start_time: datetime, duration_days: int) -> int:
        """Create new experiment record"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO experiments (start_time, duration_days)
                VALUES (?, ?)
            """, (start_time.isoformat(), duration_days))
            experiment_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Created experiment {experiment_id}")
            return experiment_id
    
    def get_current_experiment(self) -> Optional[Dict[str, Any]]:
        """Get the most recent active experiment"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM experiments 
                WHERE status = 'running'
                ORDER BY start_time DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def save_channel(self, experiment_id: int, channel_data: Dict[str, Any]) -> None:
        """Save channel configuration"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO channels 
                (channel_id, experiment_id, segment, capacity_sat, monthly_flow_msat, 
                 peer_pubkey, baseline_fee_rate, baseline_inbound_fee, 
                 current_fee_rate, current_inbound_fee, original_metrics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                channel_data['channel_id'],
                experiment_id,
                channel_data['segment'],
                channel_data['capacity_sat'],
                channel_data['monthly_flow_msat'],
                channel_data['peer_pubkey'],
                channel_data['baseline_fee_rate'],
                channel_data['baseline_inbound_fee'],
                channel_data['current_fee_rate'],
                channel_data['current_inbound_fee'],
                json.dumps(channel_data.get('original_metrics', {}))
            ))
            conn.commit()
    
    def get_experiment_channels(self, experiment_id: int) -> List[Dict[str, Any]]:
        """Get all channels for experiment"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM channels WHERE experiment_id = ?
            """, (experiment_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def save_data_point(self, experiment_id: int, data_point: Dict[str, Any]) -> None:
        """Save single data collection point"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO data_points 
                (timestamp, experiment_id, experiment_hour, channel_id, segment,
                 parameter_set, phase, outbound_fee_rate, inbound_fee_rate, base_fee_msat,
                 local_balance_sat, remote_balance_sat, local_balance_ratio,
                 forwarded_in_msat, forwarded_out_msat, fee_earned_msat, routing_events,
                 peer_fee_rates, alternative_routes, revenue_rate_per_hour,
                 flow_efficiency, balance_health_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data_point['timestamp'].isoformat(),
                experiment_id,
                data_point['experiment_hour'],
                data_point['channel_id'],
                data_point['segment'],
                data_point['parameter_set'],
                data_point['phase'],
                data_point['outbound_fee_rate'],
                data_point['inbound_fee_rate'],
                data_point['base_fee_msat'],
                data_point['local_balance_sat'],
                data_point['remote_balance_sat'],
                data_point['local_balance_ratio'],
                data_point['forwarded_in_msat'],
                data_point['forwarded_out_msat'],
                data_point['fee_earned_msat'],
                data_point['routing_events'],
                json.dumps(data_point.get('peer_fee_rates', [])),
                data_point['alternative_routes'],
                data_point['revenue_rate_per_hour'],
                data_point['flow_efficiency'],
                data_point['balance_health_score']
            ))
            conn.commit()
    
    def save_fee_change(self, experiment_id: int, fee_change: Dict[str, Any]) -> None:
        """Save fee change record"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO fee_changes 
                (timestamp, experiment_id, channel_id, parameter_set, phase,
                 old_fee, new_fee, old_inbound, new_inbound, reason, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fee_change['timestamp'],
                experiment_id,
                fee_change['channel_id'],
                fee_change['parameter_set'],
                fee_change['phase'],
                fee_change['old_fee'],
                fee_change['new_fee'],
                fee_change['old_inbound'],
                fee_change['new_inbound'],
                fee_change['reason'],
                fee_change.get('success', True)
            ))
            conn.commit()
    
    def get_recent_data_points(self, channel_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent data points for a channel"""
        cutoff = datetime.utcnow().replace(microsecond=0) - timedelta(hours=hours)
        
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM data_points 
                WHERE channel_id = ? AND timestamp > ?
                ORDER BY timestamp DESC
            """, (channel_id, cutoff.isoformat()))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_parameter_set_performance(self, experiment_id: int, parameter_set: str) -> Dict[str, Any]:
        """Get performance summary for a parameter set"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    parameter_set,
                    COUNT(DISTINCT channel_id) as channels,
                    AVG(fee_earned_msat) as avg_revenue,
                    AVG(flow_efficiency) as avg_flow_efficiency,
                    AVG(balance_health_score) as avg_balance_health,
                    SUM(fee_earned_msat) as total_revenue,
                    MIN(timestamp) as start_time,
                    MAX(timestamp) as end_time
                FROM data_points 
                WHERE experiment_id = ? AND parameter_set = ?
                GROUP BY parameter_set
            """, (experiment_id, parameter_set))
            
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def get_experiment_summary(self, experiment_id: int) -> Dict[str, Any]:
        """Get comprehensive experiment summary"""
        with self._get_connection() as conn:
            # Basic stats
            cursor = conn.execute("""
                SELECT 
                    COUNT(DISTINCT channel_id) as total_channels,
                    COUNT(*) as total_data_points,
                    MIN(timestamp) as start_time,
                    MAX(timestamp) as end_time
                FROM data_points 
                WHERE experiment_id = ?
            """, (experiment_id,))
            basic_stats = dict(cursor.fetchone())
            
            # Performance by parameter set
            cursor = conn.execute("""
                SELECT 
                    parameter_set,
                    COUNT(DISTINCT channel_id) as channels,
                    AVG(fee_earned_msat) as avg_revenue_per_point,
                    SUM(fee_earned_msat) as total_revenue,
                    AVG(flow_efficiency) as avg_flow_efficiency,
                    AVG(balance_health_score) as avg_balance_health
                FROM data_points 
                WHERE experiment_id = ?
                GROUP BY parameter_set
                ORDER BY parameter_set
            """, (experiment_id,))
            performance_by_set = [dict(row) for row in cursor.fetchall()]
            
            # Fee changes summary
            cursor = conn.execute("""
                SELECT 
                    parameter_set,
                    COUNT(*) as total_changes,
                    COUNT(CASE WHEN success THEN 1 END) as successful_changes,
                    COUNT(CASE WHEN reason LIKE '%ROLLBACK%' THEN 1 END) as rollbacks
                FROM fee_changes 
                WHERE experiment_id = ?
                GROUP BY parameter_set
                ORDER BY parameter_set
            """, (experiment_id,))
            changes_by_set = [dict(row) for row in cursor.fetchall()]
            
            # Top performing channels
            cursor = conn.execute("""
                SELECT 
                    channel_id,
                    segment,
                    AVG(fee_earned_msat) as avg_revenue,
                    SUM(fee_earned_msat) as total_revenue,
                    AVG(flow_efficiency) as avg_flow_efficiency
                FROM data_points 
                WHERE experiment_id = ?
                GROUP BY channel_id, segment
                ORDER BY total_revenue DESC
                LIMIT 10
            """, (experiment_id,))
            top_channels = [dict(row) for row in cursor.fetchall()]
            
            return {
                'basic_stats': basic_stats,
                'performance_by_parameter_set': performance_by_set,
                'changes_by_parameter_set': changes_by_set,
                'top_performing_channels': top_channels
            }
    
    def update_channel_fees(self, experiment_id: int, channel_id: str, 
                           new_outbound: int, new_inbound: int) -> None:
        """Update channel current fees"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE channels 
                SET current_fee_rate = ?, current_inbound_fee = ?
                WHERE experiment_id = ? AND channel_id = ?
            """, (new_outbound, new_inbound, experiment_id, channel_id))
            conn.commit()
    
    def get_channel_change_history(self, channel_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get fee change history for channel"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM fee_changes 
                WHERE channel_id = ? AND timestamp > ?
                ORDER BY timestamp DESC
            """, (channel_id, cutoff.isoformat()))
            return [dict(row) for row in cursor.fetchall()]
    
    def export_experiment_data(self, experiment_id: int, output_path: str) -> None:
        """Export experiment data to JSON file"""
        summary = self.get_experiment_summary(experiment_id)
        
        with self._get_connection() as conn:
            # Get all data points
            cursor = conn.execute("""
                SELECT * FROM data_points 
                WHERE experiment_id = ?
                ORDER BY timestamp
            """, (experiment_id,))
            data_points = [dict(row) for row in cursor.fetchall()]
            
            # Get all fee changes
            cursor = conn.execute("""
                SELECT * FROM fee_changes 
                WHERE experiment_id = ?
                ORDER BY timestamp
            """, (experiment_id,))
            fee_changes = [dict(row) for row in cursor.fetchall()]
            
            # Get channels
            channels = self.get_experiment_channels(experiment_id)
            
            export_data = {
                'experiment_id': experiment_id,
                'export_timestamp': datetime.utcnow().isoformat(),
                'summary': summary,
                'channels': channels,
                'data_points': data_points,
                'fee_changes': fee_changes
            }
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Exported experiment data to {output_path}")
    
    def close_experiment(self, experiment_id: int) -> None:
        """Mark experiment as completed"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE experiments 
                SET status = 'completed', end_time = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), experiment_id))
            conn.commit()
            logger.info(f"Closed experiment {experiment_id}")


# Import datetime for cutoff calculations
from datetime import timedelta