(function (jQuery) {
    var M = MochiKit;
    var MA = MochiKit.Async;
    var MB = MochiKit.Base;
    var MD = MochiKit.DOM;
    var MI = MochiKit.Iter;
    var MS = MochiKit.Style;
    var $ = MochiKit.DOM.$;
    var runAll = false;
    var stageIds = [];

    function runAllStages() {
        runAll = true;
        runStage(stageIds[0]);
    }

    var Stages = function () {
    };
    Stages.prototype.run = function (options) {
        var d = MA.loadJSONDoc("stage/?" + MB.queryString({
            'stage_id' : options.stage_id,
            'rollback_id' : options.rollback_id
        }));
        d.addCallback(options.success);
        d.addErrback(options.error);
    };

    var RunStageView = function (options) {
        var stages = options.stages;
        var stage_id = options.stage_id;
        var rollback_id = "";
        if ($('rollback')) {
            rollback_id = $('rollback').value;
        }
        stages.run(
            {
                'stage_id': stage_id,
                'rollback_id': rollback_id,
                'success': stageResults,
                'error': myErrback
            });
        var stage_row = $("stage-" + stage_id);
        MD.swapElementClass(stage_row, "unknown", "inprogress");
    };

    function runStage(stage_id) {
        var stages = new Stages();
        new RunStageView({stages: stages, stage_id: stage_id});
    }

    function myErrback(result) {
        alert("stage failed: " + result);
    }

    function makeLogTR(log, result) {
        var td = MD.TD({'colspan' : '2', 'class' : 'command'},
                       [MD.H3(null, "Code"),
                        MD.PRE(null, log.command)]);
        if (result.status === "ok") {
            hideContent(td);
        }
        return MD.TR({}, td);
    }

    function makeStdoutTR(log, result) {
        var stdouttd = MD.TD({'colspan' : '2', 'class' : 'stdout'},
                             [MD.H3(null, "STDOUT"), MD.PRE(null, log.stdout)]);
        if (result.status === "ok") {
            hideContent(stdouttd);
        }
        return MD.TR({}, stdouttd);
    }

    function makeStderrTR(log, result) {
        var stderrtd = MD.TD({'colspan' : '2', 'class' : 'stderr'},
                             [MD.H3(null, "STDERR"), MD.PRE(null, log.stderr)]);
        if (result.status === "ok") {
            hideContent(stderrtd);
        }
        return MD.TR({}, stderrtd);
    }

    function setPushStatus(result) {
        MD.swapDOM(
            $('push-status'),
            MD.DIV({'id' : 'push-status',
                    'class' : result.status}, result.status));
    }

    function makeLogRows(result) {
        var rows = [];

        for (var i = 0; i < result.logs.length; i++) {
            var log = result.logs[i];
            if (log.command) {
                rows.push(makeLogTR(log, result));
            }
            if (log.stdout) {
                rows.push(makeStdoutTR(log, result));
            }
            if (log.stderr) {
                rows.push(makeStderrTR(log, result));
            }
        }
        return rows;
    }

    function insertLogRows(stage_row, rows) {
        for (var i2 = rows.length - 1; i2 > -1; i2--) {
            MD.insertSiblingNodesAfter(stage_row, rows[i2]);
        }
    }

    // are we done or might there be more stages to run?
    function continuePush(result) {
        return runAll && (result.status !== "failed");
    }

    function nextStageOrFinish(result) {
        var nextId = getNextStageId(result.stage_id);
        if (nextId !== -1) {
            runStage(nextId);
        } else {
            setPushStatus(result);
        }
    }

    function stageResults(result) {
        var stage_row = $("stage-" + result.stage_id);

        var rows = makeLogRows(result);
        insertLogRows(stage_row, rows);

        MD.swapElementClass(stage_row, "inprogress", result.status);
        MD.swapElementClass(stage_row, "unknown", result.status);
        MD.swapDOM($("execute-" + result.stage_id), MD.SPAN(null, result.end_time));
        if (continuePush(result)) {
            nextStageOrFinish(result);
        }
        if (result.status === "failed") {
            setPushStatus(result);
        } else {
            if (!runAll) {
                if (getNextStageId(result.stage_id) === -1) {
                    // last stage
                    setPushStatus(result);
                    $('runall-button').disabled = true;
                }
            }
        }
    }

    function getNextStageId(current) {
        if (stageIds.length < 2) {
            return -1;
        }
        for (var i = 0; i < stageIds.length - 1; i++) {
            if (stageIds[i] == current) {
                return stageIds[i + 1];
            }
        }
        // reached the end without hitting it
        return -1;
    }

    function togglePre(el) {
        var pre = jQuery(jQuery(el).parent().children("pre")[0]);
        if (jQuery(el).hasClass("rolf-hidden")) {
            pre.show();
        } else {
            pre.hide();
        }
        jQuery(el).toggleClass("rolf-hidden");
        jQuery(el).toggleClass("rolf-showing");
    }

    function hideContent(td) {
        var h3 = jQuery(td).children("h3")[0];
        jQuery(td).children("pre").hide();
        jQuery(h3).addClass("rolf-hidden");
        jQuery(h3).click(function () {togglePre(h3); return false; });
    }

    function initPush() {
        jQuery("td.stdout").each(function () { hideContent(this); });
        jQuery("td.stderr").each(function () { hideContent(this); });
        jQuery("td.command").each(function () { hideContent(this); });

        MI.forEach(MD.getElementsByTagAndClassName("tr", "stage-row"),
                function (element) {
                    var stage_id = element.id.split("-")[1];
                    stageIds.push(stage_id);
                }
               );

        var autorun = jQuery('#autorun');
        if (autorun.val() === 'autorun') {
            runAllStages();
        }
    }

    MD.addLoadEvent(initPush);
}(jQuery));
