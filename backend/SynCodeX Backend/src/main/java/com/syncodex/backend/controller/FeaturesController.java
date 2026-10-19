
package com.syncodex.backend.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class FeaturesController {

    @GetMapping("/features")
    public Map<String, Object> getFeatures() {
        return Map.of(
                "application", "SynCodeX",
                "features", List.of(
                        "Code Explanation",
                        "Code Generation",
                        "Bug Detection",
                        "Codebase Search",
                        "AI Chat"
                )
        );
    }
}
