/**
 * Tests for ChooseUseCase step (CAB-1306)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { ChooseUseCase } from './ChooseUseCase';
import { renderWithProviders } from '../../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('ChooseUseCase', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    onSelect.mockReset();
  });

  it('renders the section title', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    expect(screen.getByText('chooseUseCase.title')).toBeInTheDocument();
  });

  it('renders 3 use case card buttons', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    expect(screen.getByText('chooseUseCase.mcpAgent')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.restApi')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.both')).toBeInTheDocument();
  });

  it('clicking mcp-agent card calls onSelect with "mcp-agent"', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    fireEvent.click(screen.getByText('chooseUseCase.mcpAgent'));
    expect(onSelect).toHaveBeenCalledWith('mcp-agent');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('clicking rest-api card calls onSelect with "rest-api"', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    fireEvent.click(screen.getByText('chooseUseCase.restApi'));
    expect(onSelect).toHaveBeenCalledWith('rest-api');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('clicking both card calls onSelect with "both"', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    fireEvent.click(screen.getByText('chooseUseCase.both'));
    expect(onSelect).toHaveBeenCalledWith('both');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('renders subtitle translation key', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    expect(screen.getByText('chooseUseCase.subtitle')).toBeInTheDocument();
  });

  it('renders description keys for each use case', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);
    expect(screen.getByText('chooseUseCase.mcpAgentDesc')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.restApiDesc')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.bothDesc')).toBeInTheDocument();
  });
});
