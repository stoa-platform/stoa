import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { RequestBuilder } from '../RequestBuilder';
import { renderWithProviders } from '../../../test/helpers';

describe('RequestBuilder', () => {
  const onSubmit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('initial render', () => {
    it('renders URL bar with method select and path input', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      expect(screen.getByRole('combobox')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('/api/v1/resource')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
    });

    it('shows initial method as GET', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      expect(screen.getByRole('combobox')).toHaveValue('GET');
    });

    it('shows initial path', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          initialPath="/v1/payments"
          onSubmit={onSubmit}
        />
      );
      expect(screen.getByPlaceholderText('/api/v1/resource')).toHaveValue('/v1/payments');
    });

    it('shows full URL preview', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          initialPath="/v1/orders"
          onSubmit={onSubmit}
        />
      );
      expect(screen.getByText('https://api.example.com/v1/orders')).toBeInTheDocument();
    });

    it('renders Query Params and Headers tabs', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      expect(screen.getByRole('button', { name: /Query Params/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Headers/ })).toBeInTheDocument();
    });

    it('does not show Body tab for GET method', () => {
      renderWithProviders(
        <RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} initialMethod="GET" />
      );
      expect(screen.queryByRole('button', { name: 'Body' })).not.toBeInTheDocument();
    });
  });

  describe('method selection', () => {
    it('shows Body tab when method is POST', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          onSubmit={onSubmit}
          initialMethod="POST"
        />
      );
      expect(screen.getByRole('button', { name: /Body/ })).toBeInTheDocument();
    });

    it('changing method to POST shows Body tab', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'POST' } });
      expect(screen.getByRole('button', { name: /Body/ })).toBeInTheDocument();
    });

    it('changing method to DELETE hides Body tab', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          onSubmit={onSubmit}
          initialMethod="POST"
        />
      );
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DELETE' } });
      expect(screen.queryByRole('button', { name: 'Body' })).not.toBeInTheDocument();
    });
  });

  describe('path input', () => {
    it('updates full URL when path changes', () => {
      renderWithProviders(
        <RequestBuilder baseUrl="https://api.example.com" initialPath="/" onSubmit={onSubmit} />
      );
      fireEvent.change(screen.getByPlaceholderText('/api/v1/resource'), {
        target: { value: '/v1/products' },
      });
      expect(screen.getByText('https://api.example.com/v1/products')).toBeInTheDocument();
    });
  });

  describe('headers tab', () => {
    it('shows default headers when Headers tab is clicked', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      fireEvent.click(screen.getByRole('button', { name: /Headers/ }));
      expect(screen.getByDisplayValue('Content-Type')).toBeInTheDocument();
      // application/json appears in both Content-Type and Accept values
      expect(screen.getAllByDisplayValue('application/json').length).toBeGreaterThanOrEqual(1);
    });

    it('adds a new header row when Add Header is clicked', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      fireEvent.click(screen.getByRole('button', { name: /Headers/ }));
      const initialInputs = screen.getAllByPlaceholderText('Header name');
      fireEvent.click(screen.getByRole('button', { name: 'Add Header' }));
      const afterInputs = screen.getAllByPlaceholderText('Header name');
      expect(afterInputs.length).toBe(initialInputs.length + 1);
    });

    it('removes a header when trash button is clicked', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      fireEvent.click(screen.getByRole('button', { name: /Headers/ }));
      const trashButtons = screen
        .getAllByRole('button', { name: '' })
        .filter((btn) => btn.querySelector('svg'));
      const initialCount = screen.getAllByPlaceholderText('Header name').length;
      fireEvent.click(trashButtons[0]);
      expect(screen.getAllByPlaceholderText('Header name').length).toBe(initialCount - 1);
    });
  });

  describe('query params tab', () => {
    it('shows empty params area by default', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      // Params tab is active by default
      expect(screen.getByRole('button', { name: 'Add Parameter' })).toBeInTheDocument();
    });

    it('adds a query param row when Add Parameter is clicked', () => {
      renderWithProviders(<RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} />);
      fireEvent.click(screen.getByRole('button', { name: 'Add Parameter' }));
      expect(screen.getAllByPlaceholderText('Key').length).toBe(1);
    });

    it('updates URL preview with query param', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          initialPath="/v1/orders"
          onSubmit={onSubmit}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: 'Add Parameter' }));
      const keyInputs = screen.getAllByPlaceholderText('Key');
      const valueInputs = screen.getAllByPlaceholderText('Value');
      fireEvent.change(keyInputs[0], { target: { value: 'limit' } });
      fireEvent.change(valueInputs[0], { target: { value: '10' } });
      expect(screen.getByText(/limit=10/)).toBeInTheDocument();
    });
  });

  describe('body tab', () => {
    it('shows textarea in Body tab for POST', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          onSubmit={onSubmit}
          initialMethod="POST"
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /Body/ }));
      // The textarea for body is the only textarea element
      expect(document.querySelector('textarea')).toBeInTheDocument();
    });

    it('shows Format JSON button in Body tab', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          onSubmit={onSubmit}
          initialMethod="POST"
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /Body/ }));
      expect(screen.getByRole('button', { name: 'Format JSON' })).toBeInTheDocument();
    });
  });

  describe('form submission', () => {
    it('calls onSubmit with request config when Send is clicked', () => {
      renderWithProviders(
        <RequestBuilder
          baseUrl="https://api.example.com"
          initialPath="/v1/orders"
          initialMethod="GET"
          onSubmit={onSubmit}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: 'Send' }));
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'GET',
          path: '/v1/orders',
        })
      );
    });

    it('does not call onSubmit when disabled', () => {
      renderWithProviders(
        <RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} disabled={true} />
      );
      const sendBtn = screen.getByRole('button', { name: 'Send' });
      expect(sendBtn).toBeDisabled();
    });

    it('shows loading state when isLoading=true', () => {
      renderWithProviders(
        <RequestBuilder baseUrl="https://api.example.com" onSubmit={onSubmit} isLoading={true} />
      );
      // Send button should be disabled during loading
      const sendBtn = screen.getByRole('button', { name: 'Send' });
      expect(sendBtn).toBeDisabled();
    });
  });
});
