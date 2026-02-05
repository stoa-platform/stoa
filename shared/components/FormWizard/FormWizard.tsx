import { useState, useCallback, createContext, useContext, useMemo } from 'react';
import { Check, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface WizardStep {
  id: string;
  title: string;
  description?: string;
  /** Optional validation function, returns true if step is valid */
  validate?: () => boolean | Promise<boolean>;
}

export interface FormWizardProps {
  steps: WizardStep[];
  children: React.ReactNode;
  onComplete: () => void | Promise<void>;
  /** Called when step changes */
  onStepChange?: (stepIndex: number) => void;
  /** Initial step index */
  initialStep?: number;
  /** Custom submit button label */
  submitLabel?: string;
  /** Show loading state on submit */
  isSubmitting?: boolean;
  /** Allow skipping to any step */
  allowSkip?: boolean;
}

interface WizardContextValue {
  currentStep: number;
  totalSteps: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  goToStep: (index: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  stepData: Record<string, any>;
  setStepData: (data: Record<string, any>) => void;
}

// ============================================================================
// Context
// ============================================================================

const WizardContext = createContext<WizardContextValue | null>(null);

export function useWizard() {
  const context = useContext(WizardContext);
  if (!context) {
    throw new Error('useWizard must be used within a FormWizard');
  }
  return context;
}

// ============================================================================
// Step Indicator
// ============================================================================

interface StepIndicatorProps {
  steps: WizardStep[];
  currentStep: number;
  allowSkip: boolean;
  onStepClick: (index: number) => void;
}

function StepIndicator({ steps, currentStep, allowSkip, onStepClick }: StepIndicatorProps) {
  return (
    <nav aria-label="Progress" className="mb-8">
      <ol className="flex items-center">
        {steps.map((step, index) => {
          const isComplete = index < currentStep;
          const isCurrent = index === currentStep;
          const isClickable = allowSkip || index <= currentStep;

          return (
            <li
              key={step.id}
              className={`relative ${index !== steps.length - 1 ? 'flex-1 pr-8 sm:pr-20' : ''}`}
            >
              {/* Connector line */}
              {index !== steps.length - 1 && (
                <div
                  className="absolute top-4 left-8 -right-4 sm:left-10 sm:-right-10 h-0.5"
                  aria-hidden="true"
                >
                  <div
                    className={`h-full ${isComplete ? 'bg-primary-600' : 'bg-neutral-200'}`}
                  />
                </div>
              )}

              {/* Step circle and label */}
              <button
                type="button"
                onClick={() => isClickable && onStepClick(index)}
                disabled={!isClickable}
                className={`group relative flex flex-col items-center ${
                  isClickable ? 'cursor-pointer' : 'cursor-not-allowed'
                }`}
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                    isComplete
                      ? 'bg-primary-600 text-white'
                      : isCurrent
                        ? 'border-2 border-primary-600 bg-white text-primary-600'
                        : 'border-2 border-neutral-300 bg-white text-neutral-500'
                  } ${isClickable && !isCurrent ? 'group-hover:border-primary-400' : ''}`}
                >
                  {isComplete ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </span>
                <span
                  className={`mt-2 text-xs font-medium ${
                    isCurrent ? 'text-primary-600' : 'text-neutral-500'
                  }`}
                >
                  {step.title}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ============================================================================
// Wizard Step Content Wrapper
// ============================================================================

export interface WizardStepContentProps {
  stepId: string;
  children: React.ReactNode;
}

export function WizardStepContent({ children }: WizardStepContentProps) {
  // This component is mainly for organization - actual visibility is handled by parent
  return <>{children}</>;
}

// ============================================================================
// Form Wizard
// ============================================================================

export function FormWizard({
  steps,
  children,
  onComplete,
  onStepChange,
  initialStep = 0,
  submitLabel = 'Submit',
  isSubmitting = false,
  allowSkip = false,
}: FormWizardProps) {
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [stepData, setStepData] = useState<Record<string, any>>({});
  const [isValidating, setIsValidating] = useState(false);

  const totalSteps = steps.length;
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === totalSteps - 1;
  const currentStepConfig = steps[currentStep];

  const goToStep = useCallback((index: number) => {
    if (index >= 0 && index < totalSteps) {
      setCurrentStep(index);
      onStepChange?.(index);
    }
  }, [totalSteps, onStepChange]);

  const nextStep = useCallback(async () => {
    // Validate current step if validator exists
    if (currentStepConfig.validate) {
      setIsValidating(true);
      try {
        const isValid = await currentStepConfig.validate();
        if (!isValid) {
          setIsValidating(false);
          return;
        }
      } finally {
        setIsValidating(false);
      }
    }

    if (!isLastStep) {
      goToStep(currentStep + 1);
    }
  }, [currentStep, currentStepConfig, isLastStep, goToStep]);

  const prevStep = useCallback(() => {
    if (!isFirstStep) {
      goToStep(currentStep - 1);
    }
  }, [currentStep, isFirstStep, goToStep]);

  const handleSubmit = useCallback(async () => {
    // Validate final step if validator exists
    if (currentStepConfig.validate) {
      setIsValidating(true);
      try {
        const isValid = await currentStepConfig.validate();
        if (!isValid) {
          setIsValidating(false);
          return;
        }
      } finally {
        setIsValidating(false);
      }
    }

    await onComplete();
  }, [currentStepConfig, onComplete]);

  const contextValue = useMemo<WizardContextValue>(() => ({
    currentStep,
    totalSteps,
    isFirstStep,
    isLastStep,
    goToStep,
    nextStep,
    prevStep,
    stepData,
    setStepData,
  }), [currentStep, totalSteps, isFirstStep, isLastStep, goToStep, nextStep, prevStep, stepData]);

  // Convert children to array and get current step's content
  const childArray = Array.isArray(children) ? children : [children];

  return (
    <WizardContext.Provider value={contextValue}>
      <div className="w-full">
        {/* Step indicator */}
        <StepIndicator
          steps={steps}
          currentStep={currentStep}
          allowSkip={allowSkip}
          onStepClick={goToStep}
        />

        {/* Current step info */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-neutral-900">
            {currentStepConfig.title}
          </h3>
          {currentStepConfig.description && (
            <p className="mt-1 text-sm text-neutral-500">
              {currentStepConfig.description}
            </p>
          )}
        </div>

        {/* Step content */}
        <div className="min-h-[200px]">
          {childArray[currentStep]}
        </div>

        {/* Navigation buttons */}
        <div className="mt-8 flex items-center justify-between border-t border-neutral-200 pt-6">
          <button
            type="button"
            onClick={prevStep}
            disabled={isFirstStep || isValidating || isSubmitting}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              isFirstStep
                ? 'invisible'
                : 'text-neutral-700 bg-white border border-neutral-300 hover:bg-neutral-50 disabled:opacity-50'
            }`}
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </button>

          <div className="flex items-center gap-2 text-sm text-neutral-500">
            Step {currentStep + 1} of {totalSteps}
          </div>

          {isLastStep ? (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isValidating || isSubmitting}
              className="flex items-center gap-2 px-6 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {(isValidating || isSubmitting) && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              {isSubmitting ? 'Submitting...' : submitLabel}
            </button>
          ) : (
            <button
              type="button"
              onClick={nextStep}
              disabled={isValidating}
              className="flex items-center gap-2 px-6 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {isValidating && <Loader2 className="h-4 w-4 animate-spin" />}
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </WizardContext.Provider>
  );
}

export default FormWizard;
