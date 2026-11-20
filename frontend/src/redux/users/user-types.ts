import { Dispatch } from "@reduxjs/toolkit";

export type GetAuditors = (
    dispatch: Dispatch
) => Promise<boolean>;
