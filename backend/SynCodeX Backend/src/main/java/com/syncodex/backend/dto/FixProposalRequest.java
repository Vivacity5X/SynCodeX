package com.syncodex.backend.dto;

public record FixProposalRequest(
        String file,
        String instructions,
        String error,
        String question
) {
}
