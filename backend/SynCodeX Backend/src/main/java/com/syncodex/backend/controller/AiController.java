
package com.syncodex.backend.controller;

import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import com.syncodex.backend.service.AiService;
import com.syncodex.backend.service.RepositorySessionService;
import com.syncodex.backend.dto.RepositoryContext;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.util.WebUtils;
import com.syncodex.backend.dto.McpRepositoryAnswer;
import com.syncodex.backend.dto.RepositoryAnswer;
import com.syncodex.backend.dto.RepositoryQuestionRequest;
import com.syncodex.backend.dto.DebugRequest;
import com.syncodex.backend.dto.FixProposalRequest;
import com.syncodex.backend.dto.PatchApprovalRequest;
import com.syncodex.backend.dto.PatchRevertRequest;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/ai")
public class AiController {

    private final AiService aiService;
    private final RepositorySessionService repositorySessions;

    public AiController(AiService aiService, RepositorySessionService repositorySessions) {
        this.aiService = aiService;
        this.repositorySessions = repositorySessions;
    }

    @PostMapping("/explain")
    public ExplainResponse explainCode(
            @RequestBody ExplainRequest request
    ) {
        return aiService.explainCode(request);
    }

    @PostMapping("/repository/ask")
    public RepositoryAnswer askRepository(
            @RequestBody RepositoryQuestionRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.askRepository(request, repositorySessions.current(session));
        }
    }

    @PostMapping("/repository/ask-mcp")
    public McpRepositoryAnswer askRepositoryWithMcp(
            @RequestBody RepositoryQuestionRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.askRepositoryWithMcp(request, repositorySessions.current(session));
        }
    }

    @PostMapping("/debug/analyze")
    public Map<String, Object> analyzeDebug(
            @RequestBody DebugRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.analyzeDebug(request, repositorySessions.current(session));
        }
    }

    @PostMapping("/debug/propose-fix")
    public Map<String, Object> proposeFix(
            @RequestBody FixProposalRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.proposeFix(request, repositorySessions.current(session));
        }
    }

    @PostMapping("/debug/apply-fix")
    public Map<String, Object> applyFix(
            @RequestBody PatchApprovalRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.applyFix(request, repositorySessions.current(session));
        }
    }

    @PostMapping("/debug/revert-fix")
    public Map<String, Object> revertFix(
            @RequestBody PatchRevertRequest request, HttpSession session
    ) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return aiService.revertFix(request, repositorySessions.current(session));
        }
    }

}
