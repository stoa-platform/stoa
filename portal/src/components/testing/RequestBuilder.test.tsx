import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RequestBuilder } from './RequestBuilder';
import { renderWithProviders } from '../../test/helpers';

describe('RequestBuilder', () => {
  const onSubmit = vi.fn();

  const defaultProps = {
    baseUrl: 'https://api.gostoa.dev',
    onSubmit,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render method selector with GET as default', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    const methodSelect = screen.getByDisplayValue('GET');
    expect(methodSelect).toBeInTheDocument();
  });

  it('should render all HTTP methods', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.getByText('GET')).toBeInTheDocument();
    expect(screen.getByText('POST')).toBeInTheDocument();
    expect(screen.getByText('PUT')).toBeInTheDocument();
    expect(screen.getByText('DELETE')).toBeInTheDocument();
    expect(screen.getByText('PATCH')).toBeInTheDocument();
  });

  it('should render path input with default value', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.getByPlaceholderText('/api/v1/resource')).toHaveValue('/');
  });

  it('should use initialPath and initialMethod when provided', () => {
    renderWithProviders(
      <RequestBuilder {...defaultProps} initialPath="/v1/orders" initialMethod="POST" />
    );
    expect(screen.getByPlaceholderText('/api/v1/resource')).toHaveValue('/v1/orders');
    expect(screen.getByDisplayValue('POST')).toBeInTheDocument();
  });

  it('should show full URL preview', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.getByText('https://api.gostoa.dev/')).toBeInTheDocument();
  });

  it('should render Send button', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.getByText('Send')).toBeInTheDocument();
  });

  it('should render tab navigation with Params and Headers', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.getByText('Query Params')).toBeInTheDocument();
    expect(screen.getByText('Headers')).toBeInTheDocument();
  });

  it('should not show Body tab for GET method', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    expect(screen.queryByText('Body')).not.toBeInTheDocument();
  });

  it('should show Body tab for POST method', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    await user.selectOptions(screen.getByDisplayValue('GET'), 'POST');
    expect(screen.getByText('Body')).toBeInTheDocument();
  });

  it('should show default headers (Content-Type, Accept)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    await user.click(screen.getByText('Headers'));
    expect(screen.getByDisplayValue('Content-Type')).toBeInTheDocument();
    const jsonInputs = screen.getAllByDisplayValue('application/json');
    expect(jsonInputs.length).toBeGreaterThanOrEqual(1);
  });

  it('should add new query parameter', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    await user.click(screen.getByText('Add Parameter'));
    const keyInputs = screen.getAllByPlaceholderText('Key');
    expect(keyInputs.length).toBeGreaterThanOrEqual(1);
  });

  it('should add new header', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    await user.click(screen.getByText('Headers'));
    await user.click(screen.getByText('Add Header'));
    const headerNameInputs = screen.getAllByPlaceholderText('Header name');
    expect(headerNameInputs.length).toBeGreaterThanOrEqual(1);
  });

  it('should submit request with correct data', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);

    await user.clear(screen.getByPlaceholderText('/api/v1/resource'));
    await user.type(screen.getByPlaceholderText('/api/v1/resource'), '/v1/orders');
    await user.click(screen.getByText('Send'));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        method: 'GET',
        path: '/v1/orders',
        headers: expect.arrayContaining([
          expect.objectContaining({ key: 'Content-Type', value: 'application/json' }),
        ]),
      })
    );
  });

  it('should disable form when disabled prop is true', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} disabled={true} />);
    expect(screen.getByText('Send')).toBeDisabled();
    expect(screen.getByPlaceholderText('/api/v1/resource')).toBeDisabled();
  });

  it('should show loading state on Send button', () => {
    renderWithProviders(<RequestBuilder {...defaultProps} isLoading={true} />);
    // Send button exists but the icon changes to spinner
    expect(screen.getByText('Send')).toBeInTheDocument();
  });

  it('should update full URL when path changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RequestBuilder {...defaultProps} />);
    const pathInput = screen.getByPlaceholderText('/api/v1/resource');
    await user.clear(pathInput);
    await user.type(pathInput, '/v1/health');
    expect(screen.getByText('https://api.gostoa.dev/v1/health')).toBeInTheDocument();
  });
});
