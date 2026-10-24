import {
  Field,
  FieldLabel,
  FieldInput,
  FieldTextarea,
  Form,
  FormError,
} from '@stoa/shared/components/Field';
import { Modal, ModalTitle } from '@stoa/shared/components/Modal';
import { useState, useCallback } from 'react';
import { X } from 'lucide-react';
import { federationService } from '../../services/federationApi';
import { useToastActions } from '@stoa/shared/components/Toast';
import type { SubAccountCreatedResponse } from '../../types';

interface SubAccountModalProps {
  tenantId: string;
  masterId: string;
  onClose: () => void;
  onCreated: (result: SubAccountCreatedResponse) => void;
}

export function SubAccountModal({ tenantId, masterId, onClose, onCreated }: SubAccountModalProps) {
  const toast = useToastActions();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim()) return;

      setIsSubmitting(true);
      setError(null);
      try {
        const result = await federationService.createSubAccount(tenantId, masterId, {
          name: name.trim(),
          description: description.trim() || undefined,
        });
        toast.success('Sub-account created', `${name} has been created`);
        onCreated(result);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create sub-account';
        setError(message);
        toast.error('Creation failed', message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [tenantId, masterId, name, description, toast, onCreated]
  );

  return (
    <Modal
      onClose={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex justify-between items-center mb-4">
          <ModalTitle as="h3" className="text-lg font-semibold text-neutral-900 dark:text-white">
            Create Sub-Account
          </ModalTitle>
          <button
            aria-label="Close dialog"
            type="button"
            onClick={onClose}
            className="text-muted hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <Form error={error ?? undefined} onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <FormError className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              {error}
            </FormError>
          )}
          <Field>
            <FieldLabel className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Name <span className="text-red-500">*</span>
            </FieldLabel>
            <FieldInput
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Partner Agent"
              required
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </Field>

          <Field>
            <FieldLabel className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Description
            </FieldLabel>
            <FieldTextarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              rows={2}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-neutral-700 dark:text-neutral-300 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </Form>
      </div>
    </Modal>
  );
}
