/**
 * OnboardingWizard — Guided setup for new developers (CAB-1306)
 *
 * 4-step wizard: Choose use case -> Create app -> Subscribe -> First call
 */

import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { StepIndicator } from '../../components/onboarding/StepIndicator';
import { ChooseUseCase } from '../../components/onboarding/steps/ChooseUseCase';
import { CreateApp } from '../../components/onboarding/steps/CreateApp';
import { SubscribeAPI } from '../../components/onboarding/steps/SubscribeAPI';
import { FirstCall } from '../../components/onboarding/steps/FirstCall';
import type { UseCase } from '../../components/onboarding/steps/ChooseUseCase';
import type { Application, API } from '../../types';
import { config } from '../../config';
import { loadNamespace } from '../../i18n';

export function OnboardingWizardPage() {
  const navigate = useNavigate();
  const { i18n: i18nInstance } = useTranslation('onboarding');
  const i18nEnabled = config.features.enableI18n;

  useEffect(() => {
    if (i18nEnabled) {
      const lng = i18nInstance.language;
      loadNamespace(lng, 'onboarding');
      if (lng !== 'en') loadNamespace('en', 'onboarding');
    }
  }, [i18nEnabled, i18nInstance.language]);
  const [step, setStep] = useState(0);
  const [useCase, setUseCase] = useState<UseCase>('rest-api');
  const [createdApp, setCreatedApp] = useState<Application | null>(null);
  const [selectedApi, setSelectedApi] = useState<API | null>(null);

  const handleUseCaseSelect = useCallback((uc: UseCase) => {
    setUseCase(uc);
    setStep(1);
  }, []);

  const handleAppCreated = useCallback((app: Application) => {
    setCreatedApp(app);
    setStep(2);
  }, []);

  const handleApiSelected = useCallback((api: API) => {
    setSelectedApi(api);
    setStep(3);
  }, []);

  const handleSkipSubscribe = useCallback(() => {
    setStep(3);
  }, []);

  const handleFinish = useCallback(() => {
    navigate('/');
  }, [navigate]);

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
