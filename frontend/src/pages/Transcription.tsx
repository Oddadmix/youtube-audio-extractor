import { useEffect, useState } from 'react';
import { triggerTranscription, getJobs, getChannels } from '../api';
import { Mic, RefreshCw, Layers } from 'lucide-react';
import JobStatus from '../components/JobStatus';

const Transcription = () => {
    const [jobs, setJobs] = useState<any[]>([]);
    const [channels, setChannels] = useState<any[]>([]);
    const [selectedChannels, setSelectedChannels] = useState<number[]>([]);
    const [forceRetranscribe, setForceRetranscribe] = useState(false);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        loadJobs();
        loadChannels();
        const interval = setInterval(loadJobs, 5000);
        return () => clearInterval(interval);
    }, []);

    const loadJobs = () => {
        getJobs().then(data => {
            setJobs(data.filter((j: any) => j.job_type === 'transcription'));
        });
    };

    const loadChannels = () => {
        getChannels().then(data => {
            setChannels(data);
        });
    };

    const toggleChannel = (id: number) => {
        if (selectedChannels.includes(id)) {
            setSelectedChannels(selectedChannels.filter(c => c !== id));
        } else {
            setSelectedChannels([...selectedChannels, id]);
        }
    };

    const handleSelectAll = () => {
        if (selectedChannels.length === channels.length) {
            setSelectedChannels([]);
        } else {
            setSelectedChannels(channels.map(c => c.id));
        }
    };

    const handleTranscribe = async () => {
        if (selectedChannels.length === 0) {
            alert("Please select at least one channel to transcribe.");
            return;
        }

        setLoading(true);
        try {
            await triggerTranscription({
                channel_ids: selectedChannels,
                force_retranscribe: forceRetranscribe
            });
            loadJobs();
            alert("Transcription job started!");
        } catch (err: any) {
            console.error(err);
            alert("Failed to start transcription: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <h2 style={{ marginBottom: '2rem' }}>Gemini Transcription</h2>

            <div className="stats-grid">
                <div className="card">
                    <h3 style={{ marginBottom: '1.5rem' }}>Transcription Configuration</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

                        {/* Channel Selection */}
                        <div style={{ marginBottom: '1rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                <label style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <Layers size={16} /> Select Channels ({selectedChannels.length}/{channels.length})
                                </label>
                                <button
                                    className="btn"
                                    style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem', height: 'auto' }}
                                    onClick={handleSelectAll}
                                >
                                    {selectedChannels.length === channels.length ? 'Deselect All' : 'Select All'}
                                </button>
                            </div>
                            <div style={{
                                maxHeight: '250px',
                                overflowY: 'auto',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '0.5rem',
                                paddingRight: '0.5rem'
                            }}>
                                {channels.map(channel => (
                                    <label key={channel.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                                        <input
                                            type="checkbox"
                                            checked={selectedChannels.includes(channel.id)}
                                            onChange={() => toggleChannel(channel.id)}
                                        />
                                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            {channel.name || channel.url}
                                        </span>
                                    </label>
                                ))}
                                {channels.length === 0 && <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>No channels found.</span>}
                            </div>
                        </div>

                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                            <input
                                type="checkbox"
                                checked={forceRetranscribe}
                                onChange={(e) => setForceRetranscribe(e.target.checked)}
                            />
                            Force Retranscribe (Overwrite existing)
                        </label>
                        <button className="btn btn-primary" onClick={handleTranscribe} disabled={loading || selectedChannels.length === 0}>
                            {loading ? <RefreshCw size={18} className="spin" /> : <Mic size={18} />}
                            Start Transcription
                        </button>
                    </div>
                </div>

                <div className="card">
                    <h3 style={{ marginBottom: '1rem' }}>Transcription History</h3>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                                <th style={{ padding: '1rem 0' }}>Job ID</th>
                                <th>Status</th>
                                <th>Progress</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {jobs.map(job => (
                                <tr key={job.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '1rem 0' }}>#{job.id}</td>
                                    <td style={{ padding: '0.5rem 0' }}><JobStatus job={job} /></td>
                                    <td>{job.progress}%</td>
                                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{new Date(job.created_at).toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default Transcription;
