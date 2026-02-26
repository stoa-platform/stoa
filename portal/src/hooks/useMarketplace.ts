import { useQuery } from '@tanstack/react-query';
import { marketplaceService } from '../services/marketplace';
import type { MarketplaceFilters, MarketplaceItem, MarketplaceStats } from '../types';

export function useMarketplace(filters?: MarketplaceFilters) {
  return useQuery<{ items: MarketplaceItem[]; total: number; stats: MarketplaceStats }>({
    queryKey: ['marketplace', filters],
    queryFn: () => marketplaceService.getItems(filters),
    staleTime: 30 * 1000,
  });
}

export function useFeaturedItems() {
  return useQuery<MarketplaceItem[]>({
    queryKey: ['marketplace', 'featured'],
    queryFn: () => marketplaceService.getFeaturedItems(),
    staleTime: 60 * 1000,
  });
}
