import { Suspense, lazy, useMemo } from 'react';
import { Loader2 } from 'lucide-react';

const ApiReferenceReact = lazy(() =>
  import('@scalar/api-reference-react').then((mod) => ({
    default: mod.ApiReferenceReact,
  }))
);

interface OpenAPIViewerProps {
  spec: object;
}

export function OpenAPIViewer({ spec }: OpenAPIViewerProps) {
  const specString = useMemo(() => JSON.stringify(spec), [spec]);

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 text-primary-600 animate-spin" />
        </div>
      }
    >
      <div className="scalar-viewer-container" data-testid="openapi-viewer">
        <ApiReferenceReact
          configuration={{
            content: specString,
            hideTestRequestButton: true,
            hideDownloadButton: false,
            darkMode: document.documentElement.classList.contains('dark'),
          }}
        />
      </div>
    </Suspense>
  );
}

export default OpenAPIViewer;
