import { Dispatch } from "redux";

export type Login = (
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

export type ResetPassword = (
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

export type Me = (
  dispatch: Dispatch
) => Promise<boolean>;
