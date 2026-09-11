// SPDX-License-Identifier: LGPL-2.1-or-later
// Native Gordon boolean-sum construction: profile skin + guide skin - crossing grid.
// The reparameterized sum is fitted in a shared tensor B-spline basis, then checked
// between interpolation nodes against both the sum and the original curve network.

#include <algorithm>
#include <cmath>
#include <numeric>
#include <Eigen/Dense>
#include <BRep_Tool.hxx>
#include <BRepExtrema_DistShapeShape.hxx>
#include <GeomAPI_ProjectPointOnCurve.hxx>
#include <TColgp_Array2OfPnt.hxx>
#include <TColStd_Array1OfInteger.hxx>
#include <TColStd_Array1OfReal.hxx>
#include <Base/Exception.h>

#include "GordonSurfaceBuilder.h"

namespace
{
using Matrix = Eigen::MatrixXd;
using Vector = Eigen::VectorXd;

struct SplineBasis
{
    int count;
    int degree;
    std::vector<double> knots;
    Matrix inverse;

    explicit SplineBasis(const std::vector<double>& nodes)
        : count(static_cast<int>(nodes.size()))
        , degree(std::min(3, count - 1))
    {
        knots.assign(count + degree + 1, 0.0);
        for (int i = count; i <= count + degree; ++i) {
            knots[i] = 1.0;
        }
        for (int i = 1; i < count - degree; ++i) {
            knots[i + degree] = std::accumulate(nodes.begin() + i, nodes.begin() + i + degree, 0.0)
                / degree;
        }
        Matrix interpolation(count, count);
        for (int i = 0; i < count; ++i) {
            interpolation.row(i) = values(nodes[i]).transpose();
        }
        Eigen::FullPivLU<Matrix> solver(interpolation);
        if (!solver.isInvertible()) {
            throw Base::ValueError("The curve network has degenerate interpolation parameters.");
        }
        inverse = solver.inverse();
    }

    Vector values(double parameter) const
    {
        Vector result = Vector::Zero(count + degree);
        if (parameter >= 1.0) {
            result[count - 1] = 1.0;
            return result.head(count);
        }
        for (int i = 0; i < count + degree; ++i) {
            result[i] = parameter >= knots[i] && parameter < knots[i + 1] ? 1.0 : 0.0;
        }
        for (int p = 1; p <= degree; ++p) {
            for (int i = 0; i < count + degree - p; ++i) {
                double left = knots[i + p] - knots[i];
                double right = knots[i + p + 1] - knots[i + 1];
                result[i] = (left > 0 ? (parameter - knots[i]) / left * result[i] : 0)
                    + (right > 0 ? (knots[i + p + 1] - parameter) / right * result[i + 1] : 0);
            }
        }
        return result.head(count);
    }

    Vector weights(double parameter) const
    {
        return inverse.transpose() * values(parameter);
    }

    void occKnots(TColStd_Array1OfReal& unique, TColStd_Array1OfInteger& multiplicities) const
    {
        unique.SetValue(1, 0.0);
        multiplicities.SetValue(1, degree + 1);
        for (int i = 1; i < count - degree; ++i) {
            unique.SetValue(i + 1, knots[i + degree]);
            multiplicities.SetValue(i + 1, 1);
        }
        unique.SetValue(unique.Upper(), 1.0);
        multiplicities.SetValue(unique.Upper(), degree + 1);
    }
};

struct Curve
{
    Handle(Geom_Curve) geometry;
    double first;
    double last;
};

std::vector<Curve> curves(const std::vector<TopoDS_Edge>& edges)
{
    std::vector<Curve> result;
    for (const auto& edge : edges) {
        Curve c;
        c.geometry = BRep_Tool::Curve(edge, c.first, c.last);
        if (c.geometry.IsNull() || c.last <= c.first) {
            throw Base::ValueError("The network contains a degenerate curve.");
        }
        if (c.geometry->Value(c.first).Distance(c.geometry->Value(c.last)) < 1e-7) {
            throw Base::ValueError(
                "Split closed curves at the network seam before creating a Gordon surface."
            );
        }
        result.push_back(c);
    }
    return result;
}

double parameterAt(const Curve& curve, const gp_Pnt& point)
{
    GeomAPI_ProjectPointOnCurve projection(point, curve.geometry, curve.first, curve.last);
    if (projection.NbPoints() == 0) {
        throw Base::ValueError("Could not locate a curve-network intersection.");
    }
    return projection.LowerDistanceParameter();
}

std::vector<size_t> order(const std::vector<double>& values)
{
    std::vector<size_t> result(values.size());
    std::iota(result.begin(), result.end(), 0);
    std::sort(result.begin(), result.end(), [&](size_t a, size_t b) { return values[a] < values[b]; });
    return result;
}

// Shape-preserving cubic Hermite reparameterization. It passes through every
// crossing and remains monotone, including when a source curve is reversed.
double mapParameter(double t, const std::vector<double>& x, const std::vector<double>& y)
{
    const size_t n = x.size();
    std::vector<double> slopes(n - 1), derivative(n);
    for (size_t i = 0; i + 1 < n; ++i) {
        slopes[i] = (y[i + 1] - y[i]) / (x[i + 1] - x[i]);
    }
    derivative[0] = slopes[0];
    derivative[n - 1] = slopes[n - 2];
    for (size_t i = 1; i + 1 < n; ++i) {
        const double h0 = x[i] - x[i - 1], h1 = x[i + 1] - x[i];
        derivative[i] = 3.0 * (h0 + h1)
            / ((2.0 * h1 + h0) / slopes[i - 1] + (h1 + 2.0 * h0) / slopes[i]);
    }
    const auto next = std::upper_bound(x.begin(), x.end(), t);
    const size_t i
        = std::min(n - 2, static_cast<size_t>(std::max<std::ptrdiff_t>(0, next - x.begin() - 1)));
    const double h = x[i + 1] - x[i];
    const double s = (t - x[i]) / h;
    return (2 * s * s * s - 3 * s * s + 1) * y[i] + (s * s * s - 2 * s * s + s) * h * derivative[i]
        + (-2 * s * s * s + 3 * s * s) * y[i + 1] + (s * s * s - s * s) * h * derivative[i + 1];
}

std::vector<double> commonParameters(const std::vector<std::vector<double>>& rows)
{
    std::vector<double> result(rows[0].size(), 0.0);
    for (const auto& row : rows) {
        double span = row.back() - row.front();
        if (std::abs(span) < 1e-12) {
            throw Base::ValueError("Two network intersections coincide.");
        }
        for (size_t j = 1; j < row.size(); ++j) {
            if ((row[j] - row[j - 1]) / span <= 1e-10) {
                throw Base::ValueError(
                    "The curves do not form a consistently ordered rectangular network."
                );
            }
            result[j] += (row[j] - row.front()) / span / rows.size();
        }
    }
    result.back() = 1.0;
    return result;
}

std::vector<double> sampleNodes(const std::vector<double>& crossings, int subdivisions)
{
    std::vector<double> nodes;
    for (size_t i = 0; i + 1 < crossings.size(); ++i) {
        for (int j = 0; j < subdivisions; ++j) {
            nodes.push_back(crossings[i] + (crossings[i + 1] - crossings[i]) * j / subdivisions);
        }
    }
    nodes.push_back(1.0);
    return nodes;
}
}  // namespace

Handle(Geom_BSplineSurface) Surface::buildGordonSurface(
    const std::vector<TopoDS_Edge>& profileEdges,
    const std::vector<TopoDS_Edge>& guideEdges,
    double tolerance,
    int maxSamples,
    double& approximationError
)
{
    if (profileEdges.size() < 2 || guideEdges.size() < 2) {
        throw Base::ValueError("Select at least two profiles and two guides.");
    }
    if (!std::isfinite(tolerance) || tolerance < 1e-7 || maxSamples < 8 || maxSamples > 512) {
        throw Base::ValueError("Invalid Gordon tolerance or sample limit.");
    }
    const auto profiles = curves(profileEdges), guides = curves(guideEdges);
    const size_t m = profiles.size(), n = guides.size();
    std::vector<std::vector<double>> rawU(m, std::vector<double>(n)), rawV(n, std::vector<double>(m));
    for (size_t i = 0; i < m; ++i) {
        for (size_t j = 0; j < n; ++j) {
            BRepExtrema_DistShapeShape distance(profileEdges[i], guideEdges[j]);
            if (!distance.IsDone() || distance.NbSolution() < 1 || distance.Value() > tolerance) {
                throw Base::ValueError("Every profile must intersect every guide within Tolerance.");
            }
            for (int k = 2; k <= distance.NbSolution(); ++k) {
                if (distance.PointOnShape1(k).Distance(distance.PointOnShape1(1)) > tolerance) {
                    throw Base::ValueError("A profile and guide intersect more than once; split "
                                           "the network into patches.");
                }
            }
            rawU[i][j] = parameterAt(profiles[i], distance.PointOnShape1(1));
            rawV[j][i] = parameterAt(guides[j], distance.PointOnShape2(1));
        }
    }
    const auto guideOrder = order(rawU[0]);
    const auto profileOrder = order(rawV[guideOrder[0]]);
    std::vector<std::vector<double>> u(m, std::vector<double>(n)), v(n, std::vector<double>(m));
    for (size_t i = 0; i < m; ++i) {
        for (size_t j = 0; j < n; ++j) {
            u[i][j] = rawU[profileOrder[i]][guideOrder[j]];
            v[j][i] = rawV[guideOrder[j]][profileOrder[i]];
        }
    }
    const auto commonU = commonParameters(u), commonV = commonParameters(v);
    SplineBasis cardinalU(commonU), cardinalV(commonV);
    std::vector<std::vector<gp_XYZ>> crossings(m, std::vector<gp_XYZ>(n));
    for (size_t i = 0; i < m; ++i) {
        for (size_t j = 0; j < n; ++j) {
            crossings[i][j] = (profiles[profileOrder[i]].geometry->Value(u[i][j]).XYZ()
                               + guides[guideOrder[j]].geometry->Value(v[j][i]).XYZ())
                * 0.5;
        }
    }
    auto profilePoint = [&](size_t i, double t) {
        return profiles[profileOrder[i]].geometry->Value(mapParameter(t, commonU, u[i]));
    };
    auto guidePoint = [&](size_t j, double t) {
        return guides[guideOrder[j]].geometry->Value(mapParameter(t, commonV, v[j]));
    };
    auto gordon = [&](double a, double b) {
        auto wu = cardinalU.weights(a), wv = cardinalV.weights(b);
        gp_XYZ result(0, 0, 0);
        for (size_t i = 0; i < m; ++i) {
            result += profilePoint(i, a).XYZ() * wv[i];
            for (size_t j = 0; j < n; ++j) {
                result -= crossings[i][j] * (wu[j] * wv[i]);
            }
        }
        for (size_t j = 0; j < n; ++j) {
            result += guidePoint(j, b).XYZ() * wu[j];
        }
        return gp_Pnt(result);
    };

    const int limit = (maxSamples - 1) / static_cast<int>(std::max(m, n) - 1);
    if (limit < 2) {
        throw Base::ValueError("Increase MaxSamples for this many network curves.");
    }
    for (int divisions = std::min(4, limit);; divisions = std::min(divisions * 2, limit)) {
        auto nodesU = sampleNodes(commonU, divisions), nodesV = sampleNodes(commonV, divisions);
        SplineBasis basisU(nodesU), basisV(nodesV);
        const int nu = basisU.count, nv = basisV.count;
        Matrix coordinates[3] {Matrix(nu, nv), Matrix(nu, nv), Matrix(nu, nv)};
        for (int i = 0; i < nu; ++i) {
            for (int j = 0; j < nv; ++j) {
                gp_Pnt point = gordon(nodesU[i], nodesV[j]);
                for (int k = 0; k < 3; ++k) {
                    coordinates[k](i, j) = point.Coord(k + 1);
                }
            }
        }
        for (auto& matrix : coordinates) {
            matrix = (basisU.inverse * matrix * basisV.inverse.transpose()).eval();
        }
        TColgp_Array2OfPnt poles(1, nu, 1, nv);
        for (int i = 0; i < nu; ++i) {
            for (int j = 0; j < nv; ++j) {
                poles.SetValue(
                    i + 1,
                    j + 1,
                    gp_Pnt(coordinates[0](i, j), coordinates[1](i, j), coordinates[2](i, j))
                );
            }
        }
        TColStd_Array1OfReal ku(1, nu - basisU.degree + 1), kv(1, nv - basisV.degree + 1);
        TColStd_Array1OfInteger mu(1, ku.Length()), mv(1, kv.Length());
        basisU.occKnots(ku, mu);
        basisV.occKnots(kv, mv);
        Handle(Geom_BSplineSurface) surface
            = new Geom_BSplineSurface(poles, ku, kv, mu, mv, basisU.degree, basisV.degree);
        approximationError = 0.0;
        auto check = [&](double a, double b, const gp_Pnt& expected) {
            approximationError = std::max(approximationError, surface->Value(a, b).Distance(expected));
        };
        for (int i = 0; i < nu - 1; ++i) {
            for (int sample = 1; sample <= 3; ++sample) {
                const double a = nodesU[i] + (nodesU[i + 1] - nodesU[i]) * sample / 4.0;
                for (size_t j = 0; j < m; ++j) {
                    check(a, commonV[j], profilePoint(j, a));
                }
                for (int j = 0; j < nv - 1; ++j) {
                    const double b = (nodesV[j] + nodesV[j + 1]) * 0.5;
                    check(a, b, gordon(a, b));
                }
            }
        }
        for (int j = 0; j < nv - 1; ++j) {
            for (int sample = 1; sample <= 3; ++sample) {
                const double b = nodesV[j] + (nodesV[j + 1] - nodesV[j]) * sample / 4.0;
                for (size_t i = 0; i < n; ++i) {
                    check(commonU[i], b, guidePoint(i, b));
                }
            }
        }
        if (approximationError <= tolerance) {
            return surface;
        }
        if (divisions == limit) {
            throw Base::ValueError("The Gordon fit did not reach Tolerance. Increase MaxSamples or "
                                   "simplify the network.");
        }
    }
}
