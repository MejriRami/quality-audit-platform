import { Question } from "../types";
import axiosInstance from "../services/axiosInstance";

const BASE_URL = `/question`;

export type QuestionMutationResponse =
  | Question
  | {
      message: string;
      requires_approval: boolean;
      request_id: number;
    };

export async function fetchQuestions() {
  const res = await axiosInstance.get(BASE_URL);
  return res.data as Question[];
}

export async function fetchQuestionsByQuestionnaire(questionnaire_id: number) {
  const res = await axiosInstance.get(`${BASE_URL}/getAll/${questionnaire_id}`);
  return res.data as Question[];
}

export async function createQuestion(
  question: Partial<Question>,
  questionnaire_id: number,
  requestComment?: string
) {
  try {
    const res = await axiosInstance.post(`${BASE_URL}/${questionnaire_id}`, question, {
      params: requestComment?.trim()
        ? { request_comment: requestComment.trim() }
        : undefined,
    });
    return res.data as QuestionMutationResponse;
  } catch (error: any) {
    const errorMessage =
      error?.response?.data?.detail || "An unexpected error occurred";
    throw new Error(errorMessage);
  }
}

export async function updateQuestion(
  questionId: number,
  question: Partial<Question>,
  requestComment?: string
) {
  try {
    const res = await axiosInstance.put(`${BASE_URL}/${questionId}`, question, {
      params: requestComment?.trim()
        ? { request_comment: requestComment.trim() }
        : undefined,
    });
    return res.data as QuestionMutationResponse;
  } catch (error: any) {
    const errorMessage =
      error?.response?.data?.detail || "An unexpected error occurred";
    throw new Error(errorMessage);
  }
}

export async function deleteQuestion(question_id: number, requestComment?: string) {
  try {
    const res = await axiosInstance.delete(`${BASE_URL}/${question_id}`, {
      params: requestComment?.trim()
        ? { request_comment: requestComment.trim() }
        : undefined,
    });
    return res.data as
      | { message: string }
      | { message: string; requires_approval: boolean; request_id: number };
  } catch (error: any) {
    const errorMessage =
      error?.response?.data?.detail || "An unexpected error occurred";
    throw new Error(errorMessage);
  }
}
