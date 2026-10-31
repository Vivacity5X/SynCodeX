
package com.syncodex.backend.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

public record RepositoryAnswer(
        String question,
        String answer,
        List<RepositorySource> sources,
        JsonNode project
) {
    public record RepositorySource(
            String file,
            int start_line,
            int end_line,
            double score
    ) {
    }
}
