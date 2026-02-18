/**
 * OnboardingWizard — Guided setup for new developers (CAB-1306)
 *
 * 4-step wizard: Choose use case -> Create app -> Subscribe -> First call
 */

import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { StepIndicator } from '../../components/onboarding/StepIndicator';
import { ChooseUseCase } from '../../components/onboarding/steps/ChooseUseCase';
import { CreateApp } from '../../components/onboarding/steps/CreateApp';
import { SubscribeAPI } from '../../components/onboarding/steps/SubscribeAPI';
import { FirstCall } from '../../components/onboarding/steps/FirstCall';
import { useMarkStep, useCompleteOnboarding } from '../../hooks/useOnboarding';
import type { UseCase } from '../../components/onboarding/steps/ChooseUseCase';
import type { Application, API } from '../../types';

export function OnboardingWizardPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [useCase, setUseCase] = useState<UseCase>('rest-api');
  const [createdApp, setCreatedApp] = useState<Application | null>(null);
  const [selectedApi, setSelectedApi] = useState<API | null>(null);
  const { mutate: markStepDone } = useMarkStep();
  const { mutate: completeOnboarding } = useCompleteOnboarding();

  const handleUseCaseSelect = useCallback(
    (uc: UseCase) => {
      setUseCase(uc);
      markStepDone('choose_use_case');
      setStep(1);
    },
    [markStepDone]
  );

  const handleAppCreated = useCallback(
    (app: Application) => {
      setCreatedApp(app);
      markStepDone('create_app');
      setStep(2);
    },
    [markStepDone]
  );

  const handleApiSelected = useCallback(
    (api: API) => {
      setSelectedApi(api);
      markStepDone('subscribe_api');
      setStep(3);
    },
    [markStepDone]
  );

  const handleSkipSubscribe = useCallback(() => {
    setStep(3);
  }, []);

  const handleFinish = useCallback(() => {
    markStepDone('first_call');
    completeOnboarding();
    navigate('/');
  }, [navigate, markStepDone, completeOnboarding]);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <StepIndicator currentStep={step} />

      <div className="mt-8">
        {step === 0 && <ChooseUseCase onSelect={handleUseCaseSelect} />}
        {step === 1 && <CreateApp onCreated={handleAppCreated} onBack={() => setStep(0)} />}
        {step === 2 && (
          <SubscribeAPI
            onSelected={handleApiSelected}
            onBack={() => setStep(1)}
            onSkip={handleSkipSubscribe}
          />
        )}
        {step === 3 && (
          <FirstCall
            app={createdApp}
            selectedApi={selectedApi}
            useCase={useCase}
            onFinish={handleFinish}
          />
        )}
      </div>
    </div>
  );
}
