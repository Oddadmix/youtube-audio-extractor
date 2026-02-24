import { useEffect, useState } from 'react';
import { getStats, getJobs, clearAllTasks } from '../api';
import { Trash2 } from 'lucide-react';

const Dashboard = () => {
    const [stats, setStats] = useState<any>(null);
    const [jobs, setJobs] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = () => {
        Promise.all([getStats(), getJobs()]).then(([statsData, jobsData]) => {
            setStats(statsData);
            setJobs(jobsData);
            setLoading(false);
        }).catch(err => {
            console.error(err);
            setLoading(false);
        });
    };

    const handleClearTasks = async () => {
        if (!confirm('Are you sure you want to clear the entire task queue? This will remove all pending tasks and stop active ones including downloads and exports.')) {
            return;
        }

        try {
            const res = await clearAllTasks();
            alert(res.message);
            // Reload data to reflect status changes
            loadData();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to clear queue: ${err.message}`);
        }
    };

    if (loading) return <div className="card">Loading stats...</div>;

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'completed': return 'var(--success)';
            case 'failed': return 'var(--error)';
            case 'processing': return 'var(--accent-primary)';
            default: return 'var(--text-secondary)';
        }
    };

    return (
        <div>
            <h2 style={{ marginBottom: '2rem' }}>Dashboard Overview</h2>

            <div className="stats-grid">
                <div className="card stat-card">
                    <div className="stat-label">Total Videos</div>
                    <div className="stat-value">{stats?.total_videos || 0}</div>
                </div>
                <div className="card stat-card">
                    <div className="stat-label">Processed</div>
                    <div className="stat-value" style={{ color: 'var(--success)' }}>{stats?.processed_videos || 0}</div>
                </div>
                <div className="card stat-card">
                    <div className="stat-label">Failed</div>
                    <div className="stat-value" style={{ color: 'var(--error)' }}>{stats?.failed_videos || 0}</div>
                </div>
                <div className="card stat-card">
                    <div className="stat-label">Audio Duration (hrs)</div>
                    <div className="stat-value">{stats?.total_duration_hours?.toFixed(2) || '0.00'}</div>
                </div>
            </div>

            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h3 style={{ margin: 0 }}>Recent Activity</h3>
                    <button
                        className="btn"
                        onClick={handleClearTasks}
                        style={{ background: 'var(--error)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}
                        title="Stop all running tasks and clear the waiting queue"
                    >
                        <Trash2 size={16} />
                        Clear Queue
                    </button>
                </div>
                {jobs.length === 0 ? (
                    <p style={{ color: 'var(--text-secondary)' }}>No activity logs yet. Start processing videos or exporting datasets to see activity.</p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {jobs.slice(0, 10).map((job: any) => (
                            <div key={job.id} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '0.8rem',
                                background: 'var(--bg-accent)',
                                borderRadius: 'var(--radius-md)',
                                border: '1px solid var(--border)'
                            }}>
                                <div>
                                    <div style={{ fontWeight: 500, textTransform: 'capitalize' }}>
                                        {job.job_type.replace('_', ' ')}: {job.entity_id}
                                    </div>
                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                        {new Date(job.created_at).toLocaleString()}
                                    </div>
                                </div>
                                <div style={{
                                    fontSize: '0.8rem',
                                    fontWeight: 600,
                                    color: getStatusColor(job.status),
                                    textTransform: 'uppercase'
                                }}>
                                    {job.status}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default Dashboard;
