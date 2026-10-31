package com.syncodex.backend.dto;

public record PatchRevertRequest(
        String backupId,
        String file,
        String expectedCurrentSha256,
        boolean approved
) {
}
