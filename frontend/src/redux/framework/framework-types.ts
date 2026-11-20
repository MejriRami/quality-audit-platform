import { Dispatch } from "redux";

export type GetFrameworks = (
  dispatch: Dispatch
) => Promise<boolean>;

export type AddFramework = (
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

export type DeleteFramework = (
  id: number,
  dispatch: Dispatch
) => Promise<boolean>;

export type UpdateFramework = (
  framework_id: number,
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

