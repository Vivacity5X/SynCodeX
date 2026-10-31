package com.syncodex.backend.dto;

public record DebugRequest(
        String error,
        String question,
        String logs,
        String projectContext
) {
}
