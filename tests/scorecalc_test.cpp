#include <cassert>
#include <iostream>

#include "misc.h"

using namespace Stockfish;

int main() {
    {
        ScoreCalc calc(0, 0, true);
        calc.append(NO_PIECE, 0, 7);
        assert(calc.CalcEvg() == VALUE_ZERO);
    }

    {
        ScoreCalc calc(0, 0, true);
        calc.append(NO_PIECE, -400, 1);
        calc.append(NO_PIECE, 400, 1);
        assert(std::abs(int(calc.CalcEvg())) <= 1);
    }

    {
        // The linear expectation is exactly zero. Sigmoid aggregation is
        // positive because nine modestly favorable outcomes outweigh one
        // unlikely large loss in win-probability space.
        ScoreCalc calc(0, 0, true);
        calc.append(NO_PIECE, -900, 1);
        calc.append(NO_PIECE, 100, 9);
#ifdef JIEQI_LEGACY_CHANCE_AGGREGATION
        assert(calc.CalcEvg() == VALUE_ZERO);
#else
        assert(calc.CalcEvg() > VALUE_ZERO);
#endif
    }

    {
        // Preserve Mistboard's forced-loss guard at a 50% weighted share.
        ScoreCalc calc(0, 0, true);
        const int forcedLoss = -VALUE_MATE + 10;
        calc.append(NO_PIECE, forcedLoss, 1);
        calc.append(NO_PIECE, 500, 1);
        assert(int(calc.CalcEvg()) == forcedLoss);
    }

    {
        // If every reveal wins by force, retain the slowest forced win rather
        // than flattening it through the logistic epsilon clamp.
        ScoreCalc calc(0, 0, true);
        const int slowerWin = VALUE_MATE - 20;
        const int fasterWin = VALUE_MATE - 10;
        calc.append(NO_PIECE, fasterWin, 1);
        calc.append(NO_PIECE, slowerWin, 2);
#ifdef JIEQI_LEGACY_CHANCE_AGGREGATION
        assert(int(calc.CalcEvg()) == fasterWin);
#else
        assert(int(calc.CalcEvg()) == slowerWin);
#endif
    }

    {
        // Perspective normalization must round-trip.
        ScoreCalc calc(0, 0, false);
        calc.append(NO_PIECE, 250, 1);
        assert(int(calc.CalcEvg()) > 0);
    }

    std::cout << "scorecalc tests passed\n";
    return 0;
}
