import React, { useEffect, useState } from 'react';
import { Plus, Upload, Play, Square, RotateCcw, Archive, ArchiveRestore, Eye, EyeOff } from 'lucide-react';
import { getChannels, createChannel, uploadChannelsFile, triggerChannelProcess, stopChannelProcess, resetChannel, archiveChannel, unarchiveChannel } from '../api';

interface Channel {
    id: number;
    url: string;
    name?: string;
    status: string;
    archived: boolean;
}

const Channels = () => {
    const [channels, setChannels] = useState<any[]>([]);
    const [url, setUrl] = useState('');
    const [loading, setLoading] = useState(true);
    const [showArchived, setShowArchived] = useState(false);

    useEffect(() => {
        loadChannels();
    }, [showArchived]);

    const loadChannels = () => {
        setLoading(true);
        getChannels(showArchived).then(setChannels).finally(() => setLoading(false));
    };

    const handleAddChannel = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!url) return;

        // Basic validation: ensure protocol if missing
        let targetUrl = url;
        if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
            targetUrl = 'https://' + targetUrl;
        }

        try {
            await createChannel(targetUrl);
            setUrl('');
            loadChannels();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to add channel: ${err.response?.data?.detail || err.message}`);
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            try {
                await uploadChannelsFile(e.target.files[0]);
                loadChannels();
            } catch (err: any) {
                console.error(err);
                alert(`Failed to upload file: ${err.response?.data?.detail || err.message}`);
            }
        }
    };
    const handleStop = async (id: number) => {
        try {
            await stopChannelProcess(id);
            loadChannels();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to stop process: ${err.response?.data?.detail || err.message}`);
        }
    };

    const handleReset = async (id: number) => {
        try {
            if (confirm('Are you sure you want to reset this channel? It will mark status as pending.')) {
                await resetChannel(id);
                loadChannels();
            }
        } catch (err: any) {
            console.error(err);
            alert(`Failed to reset channel: ${err.response?.data?.detail || err.message}`);
        }
    };

    const handleProcess = async (id: number) => {
        try {
            await triggerChannelProcess(id);
            loadChannels();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to trigger process: ${err.response?.data?.detail || err.message}`);
        }
    };

    const handleArchive = async (channel: Channel) => {
        try {
            if (channel.archived) {
                await unarchiveChannel(channel.id);
            } else {
                if (confirm('Are you sure you want to archive this channel? It will be excluded from default exports.')) {
                    await archiveChannel(channel.id);
                } else {
                    return;
                }
            }
            loadChannels();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to update archive status: ${err.response?.data?.detail || err.message}`);
        }
    };

    return (
        <div>
            <h2 style={{ marginBottom: '2rem' }}>Channel Management</h2>

            <div className="stats-grid">
                <div className="card">
                    <h3 style={{ marginBottom: '1rem' }}>Add Single Channel</h3>
                    <form onSubmit={handleAddChannel} style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                            type="text"
                            placeholder="YouTube Channel URL"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            style={{ flex: 1, padding: '0.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                        <button className="btn btn-primary" type="submit"><Plus size={18} /> Add</button>
                    </form>
                </div>

                <div className="card">
                    <h3 style={{ marginBottom: '1rem' }}>Bulk Import (.txt)</h3>
                    <label className="btn btn-primary" style={{ cursor: 'pointer' }}>
                        <Upload size={18} /> Upload File
                        <input type="file" accept=".txt" hidden onChange={handleFileUpload} />
                    </label>
                </div>
            </div>

            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <h3 style={{ margin: 0 }}>
                        {showArchived ? 'All Channels (Including Archived)' : 'Active Channels'}
                    </h3>

                    <button
                        className="btn"
                        onClick={() => setShowArchived(!showArchived)}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}
                    >
                        {showArchived ? <EyeOff size={16} /> : <Eye size={16} />}
                        {showArchived ? 'Hide Archived' : 'Show Archived'}
                    </button>
                </div>

                {loading ? <p>Loading channels...</p> : (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                                <th style={{ padding: '1rem 0' }}>Name/URL</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {channels.map((channel: Channel) => (
                                <tr key={channel.id} style={{ borderBottom: '1px solid var(--border)', opacity: channel.archived ? 0.6 : 1 }}>
                                    <td style={{ padding: '1rem 0' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            {channel.name || channel.url}
                                            {channel.archived && (
                                                <span style={{
                                                    fontSize: '0.7rem',
                                                    padding: '0.1rem 0.4rem',
                                                    borderRadius: '4px',
                                                    background: 'var(--text-secondary)',
                                                    color: 'var(--bg-card)'
                                                }}>ARCHIVED</span>
                                            )}
                                        </div>
                                    </td>
                                    <td>
                                        <span style={{
                                            padding: '0.2rem 0.6rem',
                                            borderRadius: 'var(--radius-sm)',
                                            backgroundColor: channel.status === 'completed' ? 'var(--success)' : 'var(--bg-accent)',
                                            fontSize: '0.8rem'
                                        }}>{channel.status}</span>
                                    </td>
                                    <td>
                                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                                            {channel.status === 'processing' ? (
                                                <button
                                                    className="btn btn-danger"
                                                    style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem', backgroundColor: 'var(--danger)' }}
                                                    onClick={() => handleStop(channel.id)}
                                                >
                                                    <Square size={14} /> Stop
                                                </button>
                                            ) : (
                                                <button
                                                    className="btn btn-primary"
                                                    style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                                                    onClick={() => handleProcess(channel.id)}
                                                    disabled={channel.status === 'processing'}
                                                >
                                                    <Play size={14} /> Process
                                                </button>
                                            )}

                                            {(channel.status === 'completed' || channel.status === 'failed') && (
                                                <button
                                                    className="btn"
                                                    style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                                                    onClick={() => handleReset(channel.id)}
                                                >
                                                    <RotateCcw size={14} /> Reset
                                                </button>
                                            )}

                                            <button className="btn" style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }} onClick={() => { }}>View Videos</button>

                                            <button
                                                className="btn"
                                                style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                                                onClick={() => handleArchive(channel)}
                                                title={channel.archived ? "Unarchive" : "Archive"}
                                            >
                                                {channel.archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default Channels;
