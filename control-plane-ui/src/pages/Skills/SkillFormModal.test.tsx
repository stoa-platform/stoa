import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SkillFormModal } from './SkillFormModal';

describe('SkillFormModal', () => {
  const onClose = vi.fn();
  const onSave = vi.fn().mockResolvedValue(undefined);

  it('renders Add Skill title when no skill provided', () => {
    render(<SkillFormModal skill={null} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Add Skill')).toBeInTheDocument();
  });

  it('renders Edit Skill title when editing', () => {
    const skill = {
      key: 'test-key',
      name: 'Test',
      description: null,
      tenant_id: 't1',
      scope: 'tenant',
      priority: 50,
      instructions: null,
      tool_ref: null,
      user_ref: null,
      enabled: true,
    };
    render(<SkillFormModal skill={skill} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Edit Skill')).toBeInTheDocument();
  });

  it('renders form fields', () => {
    render(<SkillFormModal skill={null} onClose={onClose} onSave={onSave} />);
    expect(screen.getByPlaceholderText('namespace/skill-name')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Human-readable name')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('tenant-id')).toBeInTheDocument();
  });

  it('shows Create button for new skill', () => {
    render(<SkillFormModal skill={null} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Create')).toBeInTheDocument();
  });

  it('shows Update button when editing', () => {
    const skill = {
      key: 'k',
      name: 'N',
      description: null,
      tenant_id: 't',
      scope: 'global',
      priority: 0,
      instructions: null,
      tool_ref: null,
      user_ref: null,
      enabled: true,
    };
    render(<SkillFormModal skill={skill} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Update')).toBeInTheDocument();
  });

  it('shows Cancel button', () => {
    render(<SkillFormModal skill={null} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('shows scope dropdown with all options', () => {
    render(<SkillFormModal skill={null} onClose={onClose} onSave={onSave} />);
    expect(screen.getByText('Global')).toBeInTheDocument();
  });

  it('calls onSave with payload on submit', async () => {
    const saveFn = vi.fn().mockResolvedValue(undefined);
    render(<SkillFormModal skill={null} onClose={onClose} onSave={saveFn} />);

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText('namespace/skill-name'), 'ns/test');
    await user.type(screen.getByPlaceholderText('Human-readable name'), 'My Skill');
    await user.type(screen.getByPlaceholderText('tenant-id'), 'tenant-1');

    await user.click(screen.getByText('Create'));

    await waitFor(() => {
      expect(saveFn).toHaveBeenCalledWith(
        expect.objectContaining({
          key: 'ns/test',
          name: 'My Skill',
          tenant_id: 'tenant-1',
        })
      );
    });
  });

  it('calls onClose when Cancel clicked', async () => {
    const closeFn = vi.fn();
    render(<SkillFormModal skill={null} onClose={closeFn} onSave={onSave} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(closeFn).toHaveBeenCalled();
  });

  it('disables key field when editing', () => {
    const skill = {
      key: 'existing-key',
      name: 'Existing',
      description: null,
      tenant_id: 't1',
      scope: 'global',
      priority: 50,
      instructions: null,
      tool_ref: null,
      user_ref: null,
      enabled: true,
    };
    render(<SkillFormModal skill={skill} onClose={onClose} onSave={onSave} />);
    expect(screen.getByDisplayValue('existing-key')).toBeDisabled();
  });
});
