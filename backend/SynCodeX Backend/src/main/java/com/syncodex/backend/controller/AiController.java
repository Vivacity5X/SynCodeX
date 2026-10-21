
package com.syncodex.backend.controller;

import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import com.syncodex.backend.service.AiService;
import org.springframework.web.bind.annotation.*;
import com.syncodex.backend.dto.McpRepositoryAnswer;
import com.syncodex.backend.dto.RepositoryAnswer;
import com.syncodex.backend.dto.RepositoryQuestionRequest;

@RestController
@RequestMapping("/api/v1/ai")
public class AiController {

    private final AiService aiService;

    public AiController(AiService aiService) {
        this.aiService = aiService;
    }

    @PostMapping("/explain")
    public ExplainResponse explainCode(
            @RequestBody ExplainRequest request
    ) {
        return aiService.explainCode(request);
    }

    @PostMapping("/repository/ask")
    public RepositoryAnswer askRepository(
            @RequestBody RepositoryQuestionRequest request
    ) {
        return aiService.askRepository(request);
    }

    @PostMapping("/repository/ask-mcp")
    public McpRepositoryAnswer askRepositoryWithMcp(
            @RequestBody RepositoryQuestionRequest request
    ) {
        return aiService.askRepositoryWithMcp(request);
    }

}
