import { useState } from 'react';
import { Search, Filter, Wrench, ArrowRight, Star, Clock } from 'lucide-react';

// Mock data - will be replaced with API calls
const mockTools = [
  {
    id: '1',
    name: 'text-analyzer',
    displayName: 'Text Analyzer',
    description: 'Analyze text for sentiment, entities, and key phrases',
    category: 'NLP',
    status: 'active' as const,
    rating: 4.8,
    callsToday: 1234,
  },
  {
    id: '2',
    name: 'image-classifier',
    displayName: 'Image Classifier',
    description: 'Classify images using state-of-the-art ML models',
    category: 'Vision',
    status: 'active' as const,
    rating: 4.5,
    callsToday: 892,
  },
  {
    id: '3',
    name: 'code-assistant',
    displayName: 'Code Assistant',
    description: 'AI-powered code generation and review',
    category: 'Development',
    status: 'beta' as const,
    rating: 4.9,
    callsToday: 2341,
  },
];

const categories = ['All', 'NLP', 'Vision', 'Development', 'Data', 'Automation'];

export function ToolsCatalog() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');

  const filteredTools = mockTools.filter(tool => {
    const matchesSearch = tool.displayName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === 'All' || tool.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">MCP Tools Catalog</h1>
        <p className="text-gray-500 mt-1">
          Discover and subscribe to AI-powered tools
        </p>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search tools..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-5 w-5 text-gray-400" />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Tools Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredTools.map(tool => (
          <div
            key={tool.id}
            className="bg-white rounded-lg border border-gray-200 p-5 hover:border-primary-300 hover:shadow-md transition-all cursor-pointer group"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="p-2 bg-primary-50 rounded-lg">
                <Wrench className="h-5 w-5 text-primary-600" />
              </div>
              {tool.status === 'beta' && (
                <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-700 rounded">
                  BETA
                </span>
              )}
            </div>

            <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors">
              {tool.displayName}
            </h3>
            <p className="text-sm text-gray-500 mt-1 line-clamp-2">
              {tool.description}
            </p>

            <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
              <div className="flex items-center gap-1">
                <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
                <span>{tool.rating}</span>
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                <span>{tool.callsToday.toLocaleString()} calls today</span>
              </div>
            </div>

            <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
              <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">
                {tool.category}
              </span>
              <button className="flex items-center gap-1 text-sm font-medium text-primary-600 hover:text-primary-700">
                View Details
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {filteredTools.length === 0 && (
        <div className="text-center py-12">
          <Wrench className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No tools found matching your criteria</p>
        </div>
      )}
    </div>
  );
}
