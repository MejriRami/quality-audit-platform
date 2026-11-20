import { Dispatch } from "redux";

export type GetAuditTypes = (
  dispatch: Dispatch
) => Promise<boolean>;

export type AddAuditTypes = (
  data: unknown,
  dispatch: Dispatch
) => Promise<boolean>;

export type DeleteAuditTypes = (
  id: string,
  dispatch: Dispatch
) => Promise<boolean>;

