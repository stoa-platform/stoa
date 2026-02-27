/**
 * Self-Service Signup Page — Public (no auth required) (CAB-1548)
 *
 * Allows new users to provision a trial tenant without logging in.
 */

import { useState, useCallback } from 'react';
import { signupService, type SignupRequest, type SignupResponse } from '../../services/signup';
import { StoaLogo } from '@stoa/shared/components/StoaLogo';
import { config } from '../../config';

type FormState = 'idle' | 'submitting' | 'success' | 'error';

/** Generate URL-safe slug from display name */
function toSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 63);
}

/** Validate email format */
function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function SignupPage() {
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [plan, setPlan] = useState<'trial' | 'standard'>('trial');
  const [inviteCode, setInviteCode] = useState('');
  const [formState, setFormState] = useState<FormState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [signupResult, setSignupResult] = useState<SignupResponse | null>(null);

  const slug = toSlug(displayName);
  const isFormValid = displayName.length >= 2 && isValidEmail(email) && slug.length >= 2;

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!isFormValid) return;

      setFormState('submitting');
      setErrorMessage('');

      const payload: SignupRequest = {
        name: slug,
        display_name: displayName,
        owner_email: email,
        plan,
        ...(company ? { company } : {}),
        ...(inviteCode ? { invite_code: inviteCode } : {}),
      };

      try {
        const result = await signupService.signup(payload);
        setSignupResult(result);
        setFormState('success');
      } catch (err: unknown) {
        setFormState('error');
        if (err && typeof err === 'object' && 'response' in err) {
          const axiosErr = err as { response?: { status: number; data?: { detail?: string } } };
          if (axiosErr.response?.status === 409) {
            setErrorMessage(
              'An organization with this name already exists. Please choose a different name.'
            );
          } else if (axiosErr.response?.status === 429) {
            setErrorMessage('Too many signup attempts. Please try again in a few minutes.');
          } else if (axiosErr.response?.data?.detail) {
            setErrorMessage(axiosErr.response.data.detail);
          } else {
            setErrorMessage('Something went wrong. Please try again.');
          }
        } else {
          setErrorMessage('Unable to connect to the server. Please check your connection.');
        }
      }
    },
    [isFormValid, slug, displayName, email, plan, company, inviteCode]
  );

  // Success state
  if (formState === 'success' && signupResult) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-primary-600 to-accent-600 dark:from-primary-900 dark:to-accent-900 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl max-w-md w-full p-8 text-center">
          <div className="text-4xl mb-4" aria-hidden="true">
            &#x2705;
          </div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white mb-2">
            Welcome to STOA!
          </h1>
          <p className="text-neutral-600 dark:text-neutral-400 mb-6">
            Your organization <strong>{displayName}</strong> is being provisioned.
          </p>
          <div className="bg-neutral-50 dark:bg-neutral-700 rounded-lg p-4 mb-6 text-left">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Tenant ID</dt>
                <dd className="font-mono text-neutral-900 dark:text-white">
                  {signupResult.tenant_id}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Plan</dt>
                <dd className="text-neutral-900 dark:text-white capitalize">{signupResult.plan}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-neutral-500 dark:text-neutral-400">Status</dt>
                <dd className="text-neutral-900 dark:text-white">{signupResult.status}</dd>
              </div>
            </dl>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            Check your email at <strong>{email}</strong> for login instructions.
          </p>
          <a
            href="/"
            className="inline-block py-2.5 px-6 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
          >
            Go to Portal
          </a>
        </div>
      </div>
    );
  }

  // Form
  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-600 to-accent-600 dark:from-primary-900 dark:to-accent-900 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl max-w-lg w-full p-8">
        <div className="text-center mb-6">
          <StoaLogo size="lg" />
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white mt-4">
            Create your organization
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Get started with a free trial — no credit card required
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Organization Name */}
          <div>
            <label
              htmlFor="displayName"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Organization name *
            </label>
            <input
              id="displayName"
              type="text"
              required
              minLength={2}
              maxLength={255}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Acme Corp"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              aria-label="Organization name"
            />
            {slug && (
              <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
                Slug: <span className="font-mono">{slug}</span>
              </p>
            )}
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="ownerEmail"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Email *
            </label>
            <input
              id="ownerEmail"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              aria-label="Email"
            />
          </div>

          {/* Company (optional) */}
          <div>
            <label
              htmlFor="company"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Company
            </label>
            <input
              id="company"
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Optional"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              aria-label="Company"
            />
          </div>

          {/* Plan */}
          <div>
            <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              Plan
            </span>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setPlan('trial')}
                className={`p-3 rounded-lg border-2 text-left transition-colors ${
                  plan === 'trial'
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-neutral-200 dark:border-neutral-600 hover:border-neutral-300 dark:hover:border-neutral-500'
                }`}
                aria-label="Trial plan"
              >
                <span className="block text-sm font-medium text-neutral-900 dark:text-white">
                  Trial
                </span>
                <span className="block text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  Free for 30 days
                </span>
              </button>
              <button
                type="button"
                onClick={() => setPlan('standard')}
                className={`p-3 rounded-lg border-2 text-left transition-colors ${
                  plan === 'standard'
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                    : 'border-neutral-200 dark:border-neutral-600 hover:border-neutral-300 dark:hover:border-neutral-500'
                }`}
                aria-label="Standard plan"
              >
                <span className="block text-sm font-medium text-neutral-900 dark:text-white">
                  Standard
                </span>
                <span className="block text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  Production ready
                </span>
              </button>
            </div>
          </div>

          {/* Invite Code (optional) */}
          <div>
            <label
              htmlFor="inviteCode"
              className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
            >
              Invite code
            </label>
            <input
              id="inviteCode"
              type="text"
              maxLength={64}
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="Optional"
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              aria-label="Invite code"
            />
          </div>

          {/* Error */}
          {formState === 'error' && errorMessage && (
            <div
              className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-400"
              role="alert"
            >
              {errorMessage}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={!isFormValid || formState === 'submitting'}
            className="w-full py-3 px-4 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {formState === 'submitting' ? 'Creating organization...' : 'Create Organization'}
          </button>
        </form>

        {/* Sign in link */}
        <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center mt-6">
          Already have an account?{' '}
          <a
            href="/"
            className="text-primary-600 dark:text-primary-400 hover:underline font-medium"
          >
            Sign in
          </a>
        </p>

        {/* ToS */}
        <p className="text-xs text-neutral-400 dark:text-neutral-500 text-center mt-3">
          By creating an organization, you agree to our{' '}
          <a
            href={`${config.services.docs.url}/legal/terms`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 dark:text-primary-400 hover:underline"
          >
            Terms of Service
          </a>
        </p>
      </div>
    </div>
  );
}
