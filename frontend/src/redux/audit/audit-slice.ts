// redux/audit/audit-slice.ts
import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { AuditState, AuditFilters } from "./audit-slice-types";
import {
  Audit,
  AuditCancelRequest,
  AuditPlanCreate,
  AuditDeleteResponse,

  AuditQuestion,

  AuditRescheduleHistory,
  AuditRescheduleRequest,
  ExecuteAuditRequest,
  ExecuteAuditResponse,
  PickableAudit,
} from "./audit-types";
import { apiCancelAudit, apiDeleteAudit, apiGetAudits, apiGetAuditHistory, apiPlanAudit, apiRescheduleAudit, apiGetAuditQuestions, apiGetPickableAuditsByAuditor, apiExecuteAudit } from "./audit";

const getErrorMessage = (error: unknown, fallback: string): string => {
  const err = error as { response?: { data?: { detail?: string } }; message?: string };
  return err?.response?.data?.detail || err?.message || fallback;
};

// ---------- Thunks ----------

// Load all audits
export const fetchAudits = createAsyncThunk<
  Audit[],
  void,
  { rejectValue: string }
>("audit/fetchAudits", async (_, { rejectWithValue }) => {
  try {
    const audits = await apiGetAudits();
    return audits;
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to fetch audits"));
  }
});

// Plan a new audit
export const planAuditThunk = createAsyncThunk<
  Audit,           // what API returns
  AuditPlanCreate,
  { rejectValue: string }
>("audit/planAudit", async (payload, { rejectWithValue }) => {
  try {
    const created = await apiPlanAudit(payload);
    return created;
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to plan audit"));
  }
});

// Fetch reschedule history
export const fetchAuditHistory = createAsyncThunk<
  AuditRescheduleHistory[],   // ⬅️ just the array
  number,                     // auditId as argument
  { rejectValue: string }
>("audit/fetchAuditHistory", async (auditId, { rejectWithValue }) => {
  try {
    const history = await apiGetAuditHistory(auditId);
    return history; // already an array
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to fetch audit history"));
  }
});

// Reschedule an Audit
export const rescheduleAudit = createAsyncThunk<
  Audit,
  { auditId: number; data: AuditRescheduleRequest },
  { rejectValue: string }
>("audit/rescheduleAudit", async ({ auditId, data }, { rejectWithValue }) => {
  try {
    return await apiRescheduleAudit(auditId, data);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to reschedule audit"));
  }
});

export const cancelAudit = createAsyncThunk<
  Audit,
  { auditId: number; data: AuditCancelRequest },
  { rejectValue: string }
>("audit/cancelAudit", async ({ auditId, data }, { rejectWithValue }) => {
  try {
    return await apiCancelAudit(auditId, data);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to cancel audit"));
  }
});

export const deleteAudit = createAsyncThunk<
  AuditDeleteResponse,
  number,
  { rejectValue: string }
>("audit/deleteAudit", async (auditId, { rejectWithValue }) => {
  try {
    return await apiDeleteAudit(auditId);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to delete audit"));
  }
});

//get Audit questions
export const getAuditQuestions = createAsyncThunk<
  AuditQuestion[],
  number,
  { rejectValue: string }
>("audit/getAuditQuestions", async (auditId, { rejectWithValue }) => {
  try {
    return await apiGetAuditQuestions(auditId);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to load audit questions"));
  }
});
export const fetchPickableAuditsByAuditor = createAsyncThunk<
  PickableAudit[],
  number,
  { rejectValue: string }
>("audit/fetchPickableAuditsByAuditor", async (auditorId, { rejectWithValue }) => {
  try {
    return await apiGetPickableAuditsByAuditor(auditorId);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to fetch pickable audits"));
  }
});


export const executeAuditThunk = createAsyncThunk<
  ExecuteAuditResponse,
  { auditId: number; data: ExecuteAuditRequest },
  { rejectValue: string }
>("audit/executeAudit", async ({ auditId, data }, { rejectWithValue }) => {
  try {
    return await apiExecuteAudit(auditId, data);
  } catch (error: unknown) {
    return rejectWithValue(getErrorMessage(error, "Failed to execute audit"));
  }
});
// ---------- Initial State ----------

const initialFilters: AuditFilters = {
  search: "",
  status: "",
  plant: "",
  questionnaire: "",
  dateFrom: "",
  dateTo: "",
  auditor: "",
  auditee: "",
};

const initialState: AuditState = {
  items: [],
  loading: false,
  error: null,
  calendarItems: null,
  cardsItems: null, 
  filters: initialFilters,

  historyByAuditId:[],
  historyLoading: false,
  historyError: null,

  planningLoading: false,
  planningError: null,
  rescheduleLoading: false,
  rescheduleError: null,
  cancelLoading: false,
  cancelError: null,
  pickableAudits: [],
  pickableLoading: false,
  pickableError: null,

  auditQuestions:[]

};

// ---------- Slice ----------

const auditSlice = createSlice({
  name: "audit",
  initialState,
  reducers: {
    setAuditFilters(state, action: PayloadAction<Partial<AuditFilters>>) {
      state.filters = { ...state.filters, ...action.payload };
    },
    clearAuditFilters(state) {
      state.filters = initialFilters;
    },
    getAuditorsByAuditorRequest(state) {
      state.loading = true;
      state.error = null;
    },
    getAuditorsByAuditorSuccess(state, action) {
      if (action.payload.target==='calendar')
      {
        state.calendarItems = action.payload.data;
      } else if (action.payload.target==='cards')
      {
        state.cardsItems = action.payload.data;
      }
      state.loading = false;
    },
    getAuditorsByAuditorFailure(state, action) {
      state.loading = false;
      state.error = action.payload;
    },
    removePickableAudit(state, action: PayloadAction<number>) {
  state.pickableAudits = state.pickableAudits.filter(
    (a) => a.id !== action.payload
  );
}

  },
  extraReducers: (builder) => {
    // fetchAudits
    builder
      .addCase(fetchAudits.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAudits.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload;
      })
      .addCase(fetchAudits.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || "Failed to fetch audits";
      });

    // planAuditThunk
    builder
      .addCase(planAuditThunk.pending, (state) => {
        state.planningLoading = true;
        state.planningError = null;
      })
      .addCase(planAuditThunk.fulfilled, (state, action) => {
  state.planningLoading = false;

  const createdAudit = action.payload; // full Audit

  state.items.unshift(createdAudit);
})
      .addCase(planAuditThunk.rejected, (state, action) => {
        state.planningLoading = false;
        state.planningError = action.payload || "Failed to plan audit";
      });

    // fetchAuditHistory
builder
  .addCase(fetchAuditHistory.pending, (state) => {
    state.historyLoading = true;
    state.historyError = null;
  })
  .addCase(fetchAuditHistory.fulfilled, (state, action) => {
    state.historyLoading = false;
    state.historyByAuditId = action.payload;
  })
  .addCase(fetchAuditHistory.rejected, (state, action) => {
    state.historyLoading = false;
    state.historyError = action.payload || "Failed to fetch audit history";
    state.historyByAuditId = [];
  });


    //reschedule Audit
    builder
  .addCase(rescheduleAudit.pending, (state) => {
  state.rescheduleLoading = true;
  state.rescheduleError = null;
})

.addCase(rescheduleAudit.fulfilled, (state, action) => {
  state.rescheduleLoading = false;

  const updatedAudit = action.payload;

  // replace the audit inside the state list
  const index = state.items.findIndex(a => a.id === updatedAudit.id);
  if (index !== -1) {
    state.items[index] = updatedAudit; // update existing audit
  }
})

.addCase(rescheduleAudit.rejected, (state, action) => {
  state.rescheduleLoading = false;
  state.rescheduleError = action.payload || "Failed to reschedule audit";
});
builder
  .addCase(cancelAudit.pending, (state) => {
    state.cancelLoading = true;
    state.cancelError = null;
  })
  .addCase(cancelAudit.fulfilled, (state, action) => {
    state.cancelLoading = false;
    const updatedAudit = action.payload;
    const index = state.items.findIndex((a) => a.id === updatedAudit.id);
    if (index !== -1) {
      state.items[index] = updatedAudit;
    }
  })
  .addCase(cancelAudit.rejected, (state, action) => {
  state.cancelLoading = false;
  state.cancelError = action.payload || "Failed to cancel audit";
});

    builder
      .addCase(deleteAudit.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteAudit.fulfilled, (state, action) => {
        state.loading = false;
        state.items = state.items.filter((a) => a.id !== action.payload.audit_id);
      })
      .addCase(deleteAudit.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || "Failed to delete audit";
      });
builder
.addCase(getAuditQuestions.pending, (state) => {
  state.loading = true;
  state.error = null;
})
.addCase(getAuditQuestions.fulfilled, (state, action) => {
  state.loading = false;
  state.auditQuestions = action.payload;
})
.addCase(getAuditQuestions.rejected, (state, action) => {
  state.loading = false;
  state.error = action.payload || "Failed to load audit questions";
});
builder
  .addCase(fetchPickableAuditsByAuditor.pending, (state) => {
    state.pickableLoading = true;
    state.pickableError = null;
    state.pickableAudits = [];
  })
  .addCase(fetchPickableAuditsByAuditor.fulfilled, (state, action) => {
    state.pickableLoading = false;
    state.pickableAudits = action.payload;
  })
  .addCase(fetchPickableAuditsByAuditor.rejected, (state, action) => {
    state.pickableLoading = false;
    state.pickableError = action.payload || "Failed to fetch pickable audits";
    state.pickableAudits = [];
  });
builder
  
  .addCase(executeAuditThunk.fulfilled, (state, action) => {
    const executedAuditId = action.meta.arg.auditId;

    //  remove from pickable list immediately
    state.pickableAudits = state.pickableAudits.filter(
      (a) => a.id !== executedAuditId
    );

    // optional: also update items[] if you keep global audits list
    const idx = state.items.findIndex((a) => a.id === executedAuditId);
    if (idx !== -1) {
      state.items[idx] = { ...state.items[idx], status: action.payload.status };
    }
  })
 

  },
  
});


export const { 
  setAuditFilters, 
  clearAuditFilters,
  getAuditorsByAuditorRequest,
  getAuditorsByAuditorSuccess,
  getAuditorsByAuditorFailure,
  removePickableAudit
} = auditSlice.actions;
export default auditSlice.reducer;
