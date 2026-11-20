import { Auditor, Question } from "../../types";

export interface QuestionnaireState {
    questionnairesList: Questionnaire[];
    questionnaireListName:QuestionnairesNames[];
    questionnaire: Questionnaire | null;
    success: boolean;
    error: boolean;
    toast: string;
    loading: boolean;
    deleteError:string | null;
    deleteLoading:boolean ;
}
export interface GuidelineDocument {
  id: number;
  filename: string;
  file_url: string;
  size: number;
  uploaded_at: string;
}
export interface Questionnaire {
  id: number;
  name: string;
  version: number;
  created_by?: number;
  created_at?: string;
  creation_method?: string;
  created_by_user?: {
    id?: number;
    email?: string;
    name?: string | null;
  } | null;
  approved_by_user?: {
    id?: number;
    email?: string;
    name?: string | null;
  } | null;
  approved_at?: string | null;
  status: string;
  target_duration: string;
  score_calculation: string;
  guideline_file?: string;
    guideline?: GuidelineDocument; // New guideline object from API

  type_id: string;
  framework_id: string;
  framework: {
    code: string;id:string,label:string
};
  auditType?: {id:string,value:string};
  auditors: Auditor[];
  questions: Question[];
}

export interface QuestionnairesNames{
  id: number;
  name: string;
  has_potential_analysis?: boolean;
}
