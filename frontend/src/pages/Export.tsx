import { useEffect, useState } from 'react';
import { triggerExport, getJobs, getChannels } from '../api';
import { Download, Share2, RefreshCw, Layers, Edit3 } from 'lucide-react';
import JobStatus from '../components/JobStatus';

const Export = () => {
    const [jobs, setJobs] = useState<any[]>([]);
    const [channels, setChannels] = useState<any[]>([]);
    const [selectedChannels, setSelectedChannels] = useState<number[]>([]);
    const [customNames, setCustomNames] = useState<{ [key: number]: string }>({});
    const [repoId, setRepoId] = useState('');
    const [token, setToken] = useState('');
    const [isPrivate, setIsPrivate] = useState(true);
    const [includeArchived, setIncludeArchived] = useState(false);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        loadJobs();
        loadChannels();
        const interval = setInterval(loadJobs, 5000);
        return () => clearInterval(interval);
    }, []);

    const loadJobs = () => {
        getJobs().then(data => {
            setJobs(data.filter((j: any) => j.job_type === 'export'));
        });
    };

    const loadChannels = () => {
        // Load ALL channels so we can filter locally
        getChannels(true).then(data => {
            setChannels(data);
            // Default to selecting active channels only
            const activeChannels = data.filter((c: any) => !c.archived);
            setSelectedChannels(activeChannels.map((c: any) => c.id));
        });
    };

    const toggleChannel = (id: number) => {
        if (selectedChannels.includes(id)) {
            setSelectedChannels(selectedChannels.filter(c => c !== id));
        } else {
            setSelectedChannels([...selectedChannels, id]);
        }
    };

    const handleNameChange = (id: number, name: string) => {
        setCustomNames({
            ...customNames,
            [id]: name
        });
    };

    const handleSelectAll = () => {
        // Filter visible channels based on includeArchived checkbox
        const visibleChannels = channels.filter(c => includeArchived || !c.archived);

        // Check if all visible are currently selected
        const allVisibleSelected = visibleChannels.every(c => selectedChannels.includes(c.id));

        if (allVisibleSelected) {
            // Deselect all visible
            const visibleIds = visibleChannels.map(c => c.id);
            setSelectedChannels(selectedChannels.filter(id => !visibleIds.includes(id)));
        } else {
            // Select all visible
            const visibleIds = visibleChannels.map(c => c.id);
            // Merge unique IDs
            const newSelection = Array.from(new Set([...selectedChannels, ...visibleIds]));
            setSelectedChannels(newSelection);
        }
    };

    const handleExport = async () => {
        if (selectedChannels.length === 0) {
            alert("Please select at least one channel to export.");
            return;
        }

        setLoading(true);
        try {
            // Convert customNames keys to strings for API
            const channelNamesStr: { [key: string]: string } = {};
            selectedChannels.forEach(id => {
                if (customNames[id]) {
                    channelNamesStr[id.toString()] = customNames[id];
                }
            });

            await triggerExport({
                repo_id: repoId,
                hf_token: token,
                private: isPrivate,
                channel_ids: selectedChannels,
                channel_names: channelNamesStr,
                include_archived: includeArchived
            });
            loadJobs();
            alert("Export job started!");
        } catch (err: any) {
            console.error(err);
            alert("Failed to start export: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <h2 style={{ marginBottom: '2rem' }}>HuggingFace Export</h2>

            <div className="stats-grid">
                <div className="card">
                    <h3 style={{ marginBottom: '1.5rem' }}>Dataset Configuration</h3>
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
                            <div style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                    <input
                                        type="checkbox"
                                        checked={includeArchived}
                                        onChange={(e) => setIncludeArchived(e.target.checked)}
                                    />
                                    Show & Include Archived Channels
                                </label>
                            </div>
                            <div style={{
                                maxHeight: '150px',
                                overflowY: 'auto',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '0.5rem',
                                paddingRight: '0.5rem'
                            }}>
                                {channels
                                    .filter(channel => includeArchived || !channel.archived)
                                    .map(channel => (
                                        <div key={channel.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'space-between', opacity: channel.archived ? 0.7 : 1 }}>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem', flex: 1, overflow: 'hidden' }}>
                                                <input
                                                    type="checkbox"
                                                    checked={selectedChannels.includes(channel.id)}
                                                    onChange={() => toggleChannel(channel.id)}
                                                />
                                                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                    {channel.name || channel.url}
                                                </span>
                                                {channel.archived && (
                                                    <span style={{ fontSize: '0.6rem', padding: '0 0.3rem', background: 'var(--text-secondary)', color: 'black', borderRadius: '4px' }}>ARCHIVED</span>
                                                )}
                                            </label>

                                            {/* Custom Name Input */}
                                            {selectedChannels.includes(channel.id) && (
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                    <Edit3 size={14} color="var(--text-secondary)" />
                                                    <input
                                                        type="text"
                                                        placeholder="Subset Name (optional)"
                                                        value={customNames[channel.id] || ''}
                                                        onChange={(e) => handleNameChange(channel.id, e.target.value)}
                                                        onClick={(e) => e.stopPropagation()}
                                                        style={{
                                                            padding: '0.2rem 0.4rem',
                                                            fontSize: '0.8rem',
                                                            borderRadius: 'var(--radius-sm)',
                                                            border: '1px solid var(--border)',
                                                            background: 'var(--bg-main)',
                                                            color: 'white',
                                                            width: '140px'
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                {channels.filter(c => includeArchived || !c.archived).length === 0 && <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>No channels found.</span>}
                            </div>
                        </div>

                        <input
                            type="text"
                            placeholder="Repo ID (e.g., username/egyptian-asr)"
                            value={repoId}
                            onChange={(e) => setRepoId(e.target.value)}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                        <input
                            type="password"
                            placeholder="HuggingFace Token (optional)"
                            value={token}
                            onChange={(e) => setToken(e.target.value)}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem' }}>
                            <input
                                type="checkbox"
                                checked={isPrivate}
                                onChange={(e) => setIsPrivate(e.target.checked)}
                            />
                            Private Dataset
                        </label>
                        <button className="btn btn-primary" onClick={handleExport} disabled={loading || selectedChannels.length === 0}>
                            {loading ? <RefreshCw size={18} className="spin" /> : <Share2 size={18} />}
                            Generate & Push to Hub
                        </button>
                    </div>
                </div>

                <div className="card">
                    <h3 style={{ marginBottom: '1.5rem' }}>Local Download</h3>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
                        Generate the dataset locally and download it as a Parquet file.
                    </p>
                    <a href="/api/export/download" className="btn btn-primary" style={{ width: 'fit-content' }}>
                        <Download size={18} /> Download Parquet
                    </a>
                </div>
            </div>

            <div className="card">
                <h3 style={{ marginBottom: '1rem' }}>Export History</h3>
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
    );
};

export default Export;
