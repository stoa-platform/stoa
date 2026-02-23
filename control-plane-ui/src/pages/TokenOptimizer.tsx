import { Coins } from 'lucide-react';

export function TokenOptimizer() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Token Optimizer</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-2">
          Analyze and optimize token usage across your MCP tool invocations
        </p>
      </div>

      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-8 text-center">
        <div className="w-16 h-16 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <Coins className="h-8 w-8 text-primary-600 dark:text-primary-400" />
        </div>
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">Coming Soon</h2>
        <p className="text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">
          Token Optimizer will provide insights into your LLM token consumption, identify wasteful
          patterns, and suggest optimizations to reduce costs.
        </p>
      </div>
    </div>
  );
}

export default TokenOptimizer;
