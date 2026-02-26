/**
 * Favorites / Bookmarks Page (CAB-1470)
 */

import { Star, Trash2, ExternalLink } from 'lucide-react';
import { useFavorites, useRemoveFavorite } from '../../hooks/useFavorites';
import { useAuth } from '../../contexts/AuthContext';
import type { Favorite } from '../../types';

function FavoriteCard({
  favorite,
  onRemove,
  isRemoving,
}: {
  favorite: Favorite;
  onRemove: (id: string) => void;
  isRemoving: boolean;
}) {
  const href =
    favorite.item_type === 'api' ? `/apis/${favorite.item_id}` : `/mcp-servers/${favorite.item_id}`;

  return (
    <div className="flex items-start gap-4 p-4 bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700">
      <Star className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5 fill-amber-500" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <a
            href={href}
            className="text-sm font-medium text-neutral-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400 truncate"
          >
            {favorite.item_name}
          </a>
          <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400">
            {favorite.item_type === 'api' ? 'API' : 'MCP Server'}
          </span>
        </div>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1 line-clamp-2">
          {favorite.item_description}
        </p>
        <div className="flex items-center gap-3 mt-2">
          <time className="text-xs text-neutral-400">
            Added {new Date(favorite.added_at).toLocaleDateString()}
          </time>
          <a
            href={href}
            className="text-xs text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-1"
          >
            View <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
      <button
        onClick={() => onRemove(favorite.id)}
        disabled={isRemoving}
        className="p-2 text-neutral-400 hover:text-red-500 transition-colors disabled:opacity-50"
        aria-label={`Remove ${favorite.item_name} from favorites`}
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

export function FavoritesPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { data, isLoading } = useFavorites();
  const removeFavorite = useRemoveFavorite();

  if (authLoading || !isAuthenticated) {
    return null;
  }

  const favorites = data?.favorites ?? [];

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Star className="w-6 h-6 text-amber-500 fill-amber-500" />
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Favorites</h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Your bookmarked APIs and MCP servers
            </p>
          </div>
        </div>

        {/* List */}
        {isLoading ? (
          <div className="text-center py-8 text-neutral-400">Loading favorites...</div>
        ) : favorites.length === 0 ? (
          <div className="text-center py-16">
            <Star className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
            <h2 className="text-lg font-medium text-neutral-600 dark:text-neutral-300">
              No favorites yet
            </h2>
            <p className="text-sm text-neutral-400 mt-1">
              Bookmark APIs and MCP servers from their detail pages
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {favorites.map((fav) => (
              <FavoriteCard
                key={fav.id}
                favorite={fav}
                onRemove={(id) => removeFavorite.mutate(id)}
                isRemoving={removeFavorite.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default FavoritesPage;
