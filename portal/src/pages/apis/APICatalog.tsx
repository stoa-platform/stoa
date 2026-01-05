import { BookOpen, Construction } from 'lucide-react';

export function APICatalog() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">API Catalog</h1>
        <p className="text-gray-500 mt-1">
          Browse and discover available APIs
        </p>
      </div>

      {/* Coming Soon */}
      <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
        <div className="inline-flex p-4 bg-amber-50 rounded-full mb-4">
          <Construction className="h-8 w-8 text-amber-600" />
        </div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Coming Soon</h2>
        <p className="text-gray-500 max-w-md mx-auto">
          The API Catalog is currently under development. Soon you'll be able to browse,
          search, and subscribe to APIs from this page.
        </p>
        <div className="mt-6 flex justify-center gap-4">
          <a
            href="/tools"
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            Browse MCP Tools Instead
          </a>
        </div>
      </div>

      {/* Preview */}
      <div className="bg-gray-50 rounded-lg border border-gray-200 p-6">
        <h3 className="font-medium text-gray-900 mb-4">What to expect:</h3>
        <ul className="space-y-2 text-gray-600">
          <li className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary-600" />
            Browse REST and GraphQL APIs
          </li>
          <li className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary-600" />
            Interactive API documentation
          </li>
          <li className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary-600" />
            Try APIs directly from the browser
          </li>
          <li className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-primary-600" />
            Generate client code in multiple languages
          </li>
        </ul>
      </div>
    </div>
  );
}
