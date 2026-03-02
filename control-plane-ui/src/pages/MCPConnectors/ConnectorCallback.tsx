import { useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { mcpConnectorsService } from '../../services/mcpConnectorsApi';
import { useToastActions } from '@stoa/shared/components/Toast';
import { StoaLoader } from '@stoa/shared/components/StoaLoader';

export function ConnectorCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToastActions();
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;

    const error = searchParams.get('error');
    if (error) {
      const description = searchParams.get('error_description') || 'Authorization was denied';
      toast.error('Connection failed', description);
      navigate('/mcp-connectors', { replace: true });
      return;
    }

    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code || !state) {
      toast.error('Connection failed', 'Missing authorization parameters');
      navigate('/mcp-connectors', { replace: true });
      return;
    }

    mcpConnectorsService
      .handleCallback({ code, state })
      .then((response) => {
        toast.success('Connected', `${response.display_name} has been connected`);
        if (response.redirect_url) {
          navigate(response.redirect_url, { replace: true });
        } else {
          navigate(`/external-mcp-servers/${response.server_id}`, { replace: true });
        }
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Failed to complete authorization';
        toast.error('Connection failed', message);
        navigate('/mcp-connectors', { replace: true });
      });
  }, [searchParams, navigate, toast]);

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center space-y-4">
        <StoaLoader variant="inline" />
        <p className="text-neutral-500 dark:text-neutral-400">Connecting...</p>
      </div>
    </div>
  );
}
