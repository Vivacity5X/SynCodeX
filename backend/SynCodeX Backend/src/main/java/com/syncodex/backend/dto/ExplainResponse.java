
package com.syncodex.backend.dto;

public record ExplainResponse(
        String application,
        String language,
        String explanation,
        String status
) {
}
