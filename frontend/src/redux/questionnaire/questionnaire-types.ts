import { Dispatch } from "redux";

export type GetQuestionnaires = (
  dispatch: Dispatch
) => Promise<boolean>;

export type GetQuestionnaireById = (
  id: number,
  dispatch: Dispatch
) => Promise<boolean>;

export type AddQuestionnaire = (
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

export type DeleteQuestionnaire = (
  id: number,
  dispatch: Dispatch
) => Promise<{
  success: boolean;
  deleted?: boolean;
  request_submitted?: boolean;
  message?: string;
  error?: string;
  status?: number;
}>;

export type UpdateQuestionnaire = (
  questionnaire_id: number,
  data: {
    name?: string;
    status?: string;
    target_duration?: string;
    type_id?: number;
    framework_id?: number;
    auditor_emails?: string[];
  },
  file: File | null,
  removeGuideline: boolean,
  dispatch: Dispatch,
  currentUserId: number  
) => Promise<{
  success: boolean;
  requiresApproval?: boolean;
  message?: string;
}>;

export type GetQuestionnairesByName=(
 dispatch: Dispatch
) => Promise<boolean>;


