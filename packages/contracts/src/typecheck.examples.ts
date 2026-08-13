import type {
  CorrelationId,
  ErrorEnvelope,
  PaginationMeta,
  SuccessEnvelope,
} from "./index";

const pagination: PaginationMeta = {
  page: 1,
  pageSize: 25,
  total: 0,
  totalPages: 0,
};

const success: SuccessEnvelope<readonly string[], PaginationMeta> = {
  data: [],
  meta: pagination,
};

const failure: ErrorEnvelope = {
  error: {
    code: "VALIDATION_ERROR",
    message: "Request validation failed.",
    fields: {
      fieldName: "Human-readable field error.",
    },
  },
};

const correlationId: CorrelationId = "request-correlation-id";

void success;
void failure;
void correlationId;
