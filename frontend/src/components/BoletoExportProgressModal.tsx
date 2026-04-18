import React, { useEffect, useState } from 'react';
import { fetchJson, downloadFile } from '../lib/api';
import { BoletoExportJob } from '../types';
import './BoletoExportProgressModal.css';

interface Props {
  jobId: string;
  onClose: () => void;
}

export const BoletoExportProgressModal: React.FC<Props> = ({ jobId, onClose }) => {
  const [job, setJob] = useState<BoletoExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: number;

    const poll = async () => {
      try {
        const data = await fetchJson<BoletoExportJob>(`/boletos/inter/export/${jobId}`);
        setJob(data);

        if (data.status === 'completed') {
          // Trigger download and close
          await downloadFile(`/boletos/inter/export/${jobId}/file`, {
            filename: data.filename || 'export.pdf'
          });
          onClose();
        } else if (data.status === 'failed') {
          setError(data.error_message || 'Erro desconhecido durante a exportação.');
        } else {
          timer = window.setTimeout(poll, 2000);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Falha ao consultar status do trabalho.');
      }
    };

    poll();
    return () => window.clearTimeout(timer);
  }, [jobId, onClose]);

  const progress = job ? (job.total_count > 0 ? (job.processed_count / job.total_count) * 100 : 0) : 0;
  const statusLabel = job?.status === 'processing' 
    ? `Processando ${job.processed_count} de ${job.total_count}...`
    : job?.status === 'pending'
    ? 'Aguardando início...'
    : job?.status === 'completed'
    ? 'Concluído!'
    : job?.status === 'failed'
    ? 'Falha na exportação'
    : 'Iniciando...';

  return (
    <div className="export-progress-overlay">
      <div className="export-progress-modal">
        <h3 className="export-progress-title">Preparando Exportação</h3>
        
        <div className="export-progress-container">
          <div className="export-progress-bar-bg">
            <div 
              className="export-progress-bar-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="export-status-text">{statusLabel}</div>
        </div>

        {error && (
          <div className="export-error-box">
            <strong>Erro:</strong> {error}
          </div>
        )}

        <div className="export-footer">
          <button 
            type="button"
            className="secondary-button" 
            onClick={onClose}
          >
            {job?.status === 'failed' ? 'Fechar' : 'Cancelar'}
          </button>
        </div>
      </div>
    </div>
  );
};
