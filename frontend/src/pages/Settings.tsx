import React, { useEffect, useState } from 'react';
import { Save, RefreshCcw } from 'lucide-react';
import { getSettings, updateSettings } from '../api';

const Settings = () => {
    const [settings, setSettings] = useState({
        sample_rate: 16000,
        silence_thresh: -40,
        min_silence_len: 700,
        min_chunk_len: 1, // Store as seconds for UI
        max_chunk_len: 20, // Store as seconds for UI
        retry_count: 3,
        transcription_prompt: "",
        vad_threshold: 0.25,
        min_speech_duration_ms: 250,
        speaker_similarity_threshold: 0.75
    });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        getSettings().then(data => {
            setSettings({
                ...data,
                min_chunk_len: data.min_chunk_len / 1000,
                max_chunk_len: data.max_chunk_len / 1000
            });
            setLoading(false);
        }).catch(err => {
            console.error(err);
            setLoading(false);
        });
    }, []);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { name, value } = e.target;
        setSettings(prev => ({ ...prev, [name]: parseFloat(value) }));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            // Convert seconds back to milliseconds for backend
            const backendData = {
                ...settings,
                min_chunk_len: Math.round(settings.min_chunk_len * 1000),
                max_chunk_len: Math.round(settings.max_chunk_len * 1000)
            };
            await updateSettings(backendData);
            alert('Settings saved successfully!');
        } catch (err: any) {
            console.error(err);
            alert(`Failed to save settings: ${err.response?.data?.detail || err.message}`);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="card">Loading settings...</div>;

    return (
        <div>
            <h2 style={{ marginBottom: '2rem' }}>Processing Settings</h2>

            <div className="card" style={{ maxWidth: '600px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Sample Rate (Hz)</label>
                        <input
                            name="sample_rate"
                            type="number"
                            value={settings.sample_rate}
                            onChange={handleChange}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Silence Threshold (dB)</label>
                        <input
                            name="silence_thresh"
                            type="number"
                            value={settings.silence_thresh}
                            onChange={handleChange}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Min Silence (ms)</label>
                            <input
                                name="min_silence_len"
                                type="number"
                                value={settings.min_silence_len}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Retry Count</label>
                            <input
                                name="retry_count"
                                type="number"
                                value={settings.retry_count}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Min Chunk (s)</label>
                            <input
                                name="min_chunk_len"
                                type="number"
                                step="0.1"
                                value={settings.min_chunk_len}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Max Chunk (s)</label>
                            <input
                                name="max_chunk_len"
                                type="number"
                                step="0.1"
                                value={settings.max_chunk_len}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                    </div>



                    <hr style={{ borderColor: 'var(--border)', margin: '1rem 0' }} />

                    <h3 style={{ fontSize: '1.2rem', marginBottom: '1rem', color: 'var(--primary)' }}>Advanced VAD Settings</h3>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>VAD Threshold (0.0 - 1.0)</label>
                            <input
                                name="vad_threshold"
                                type="number"
                                step="0.05"
                                min="0"
                                max="1"
                                value={settings.vad_threshold}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Min Speech Duration (ms)</label>
                            <input
                                name="min_speech_duration_ms"
                                type="number"
                                value={settings.min_speech_duration_ms}
                                onChange={handleChange}
                                style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                            />
                        </div>
                    </div>

                    <hr style={{ borderColor: 'var(--border)', margin: '1rem 0' }} />

                    <h3 style={{ fontSize: '1.2rem', marginBottom: '1rem', color: 'var(--primary)' }}>Transcription</h3>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>System Prompt</label>
                        <textarea
                            name="transcription_prompt"
                            value={settings.transcription_prompt}
                            onChange={(e) => setSettings(prev => ({ ...prev, transcription_prompt: e.target.value }))}
                            rows={6}
                            style={{
                                width: '100%',
                                padding: '0.8rem',
                                borderRadius: 'var(--radius-md)',
                                border: '1px solid var(--border)',
                                background: 'var(--bg-accent)',
                                color: 'white',
                                fontFamily: 'monospace',
                                lineHeight: '1.5',
                                resize: 'vertical'
                            }}
                        />
                        <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.5rem' }}>
                            Instructions for the AI model on how to transcribe the audio.
                        </small>
                    </div>

                    <hr style={{ borderColor: 'var(--border)', margin: '1rem 0' }} />

                    <h3 style={{ fontSize: '1.2rem', marginBottom: '1rem', color: 'var(--primary)' }}>Speaker Identification</h3>

                    <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Speaker Similarity Threshold (0.0 - 1.0)</label>
                        <input
                            name="speaker_similarity_threshold"
                            type="number"
                            step="0.05"
                            min="0"
                            max="1"
                            value={settings.speaker_similarity_threshold}
                            onChange={handleChange}
                            style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-accent)', color: 'white' }}
                        />
                        <small style={{ color: 'var(--text-secondary)', display: 'block', marginTop: '0.5rem' }}>
                            Threshold for matching voices to speakers. Higher = more unique speakers created (0.85-0.95 conservative, 0.60-0.75 aggressive grouping).
                        </small>
                    </div>

                    <button
                        className="btn btn-primary"
                        style={{ marginTop: '1rem' }}
                        onClick={handleSave}
                        disabled={saving}
                    >
                        {saving ? <RefreshCcw className="animate-spin" size={18} /> : <Save size={18} />}
                        {saving ? ' Saving...' : ' Save Settings'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Settings;
