package com.syncodex.backend.dto;

public record PatchApprovalRequest(
        String proposalId,
        boolean approved
) {
}
