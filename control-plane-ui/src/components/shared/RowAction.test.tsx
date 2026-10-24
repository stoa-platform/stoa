import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { RowAction } from '@stoa/shared/components/RowAction';

describe('table RowAction', () => {
  it('activates once with Enter, Space and pointer, and keeps secondary actions independent', async () => {
    const action = vi.fn(),
      secondary = vi.fn();
    const user = userEvent.setup();
    render(
      <table>
        <tbody>
          <tr onClick={action}>
            <td>
              <RowAction onActivate={action}>Example consumer</RowAction>
            </td>
            <td onClick={(event) => event.stopPropagation()}>
              <button onClick={secondary}>Suspend</button>
            </td>
          </tr>
        </tbody>
      </table>
    );
    await user.tab();
    expect(screen.getByRole('button', { name: 'Example consumer' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(action).toHaveBeenCalledTimes(1);
    await user.keyboard(' ');
    expect(action).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole('button', { name: 'Example consumer' }));
    expect(action).toHaveBeenCalledTimes(3);
    await user.tab();
    await user.keyboard('{Enter}');
    expect(secondary).toHaveBeenCalledOnce();
    expect(action).toHaveBeenCalledTimes(3);
  });
});
