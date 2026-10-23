import { CheckCircle, RefreshCw, AlertCircle, Clock } from 'lucide-react';

const LABELS: Record<string, string> = {
    pending: 'queued',
    processing: 'running',
    completed: 'completed',
    failed: 'failed',
};

const JobStatus = ({ job }: { job: { status: string; error_message?: string | null } }) => {
    const icon = job.status === 'completed' ? <CheckCircle size={16} color="var(--success)" />
        : job.status === 'failed' ? <AlertCircle size={16} color="var(--error)" />
        : job.status === 'processing' ? <RefreshCw size={16} className="spin" />
        : <Clock size={16} color="var(--text-secondary)" />;

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {icon}
                {LABELS[job.status] ?? job.status}
            </div>
            {job.error_message && (
                <div
                    title={job.error_message}
                    style={{ color: 'var(--error)', fontSize: '0.8rem', marginTop: '0.25rem', maxWidth: '32rem', wordBreak: 'break-word' }}
                >
                    {job.error_message}
                </div>
            )}
        </div>
    );
};

export default JobStatus;
