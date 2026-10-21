
package com.syncodex.backend.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record McpRepositoryAnswer(
        String question,
        String answer,
        JsonNode sources
) {
}
