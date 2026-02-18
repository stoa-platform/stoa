import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { ChooseUseCase } from '../ChooseUseCase';
import { renderWithProviders } from '../../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

describe('ChooseUseCase', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    onSelect.mockReset();
  });

  it('renders title via i18n', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.title')).toBeInTheDocument();
  });

  it('renders subtitle via i18n', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.subtitle')).toBeInTheDocument();
  });

  it('renders 3 use case buttons', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
  });

  it('renders mcp-agent option title', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.mcpAgent')).toBeInTheDocument();
  });

  it('renders rest-api option title', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.restApi')).toBeInTheDocument();
  });

  it('renders both option title', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.both')).toBeInTheDocument();
  });

  it('calls onSelect with mcp-agent when first button clicked', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[0]);

    expect(onSelect).toHaveBeenCalledWith('mcp-agent');
  });

  it('calls onSelect with rest-api when second button clicked', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[1]);

    expect(onSelect).toHaveBeenCalledWith('rest-api');
  });

  it('calls onSelect with both when third button clicked', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[2]);

    expect(onSelect).toHaveBeenCalledWith('both');
  });

  it('renders description for each use case', () => {
    renderWithProviders(<ChooseUseCase onSelect={onSelect} />);

    expect(screen.getByText('chooseUseCase.mcpAgentDesc')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.restApiDesc')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.bothDesc')).toBeInTheDocument();
  });
});
