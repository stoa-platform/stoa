import { useParams } from 'react-router-dom';

export function FederationAccountDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Federation Account Detail
      </h1>
      <p className="text-gray-500 dark:text-neutral-400">
        Account ID: {id} — Detail view coming in next PR.
      </p>
    </div>
  );
}
