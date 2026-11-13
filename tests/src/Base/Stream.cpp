// SPDX-License-Identifier: LGPL-2.1-or-later

#include <array>

#include <gtest/gtest.h>

#include <Python.h>

#include <CXX/Objects.hxx>

#ifdef _MSC_VER
# pragma warning(disable : 4996)
#endif

#include "Base/Stream.h"


class TextOutputStreamTest: public ::testing::Test
{
protected:
    void SetUp() override
    {}

    void TearDown() override
    {}
};

TEST_F(TextOutputStreamTest, singleLineCharStar)
{
    // Arrange
    const std::string testString("Single line const char *");
    std::ostringstream ss;
    Base::TextOutputStream tos(ss);

    // Act
    tos << testString;

    // Assert - the number of newlines in the string, a colon, the string, a newline
    EXPECT_EQ(std::string("0:") + testString + "\n", ss.str());
}

TEST_F(TextOutputStreamTest, multiLineCharStar)
{
    // Arrange
    const std::string testString("Multi-line\nconst char *");
    std::ostringstream ss;
    Base::TextOutputStream tos(ss);

    // Act
    tos << testString;  // Testing it with a string instead of a const char * -- failing right now

    // Assert - the number of newlines in the string, a colon, the string, a newline
    EXPECT_EQ(std::string("1:") + testString + "\n", ss.str());
}

TEST_F(TextOutputStreamTest, singleLineCharStarWithCarriageReturns)
{
    // Arrange
    const std::string testString("Single-line\rconst char *");
    std::ostringstream ss;
    Base::TextOutputStream tos(ss);

    // Act
    tos << testString;

    // Assert - the number of newlines in the string, a colon, the string, a newline. Carriage
    // returns are left alone because they aren't followed by a newline
    EXPECT_EQ(std::string("0:") + testString + "\n", ss.str());
}

TEST_F(TextOutputStreamTest, multiLineCharStarWithCarriageReturnsAndNewlines)
{
    // Arrange
    const std::string testString("Multi-line\r\nconst char *");
    const std::string testStringWithoutCR("Multi-line\nconst char *");
    std::ostringstream ss;
    Base::TextOutputStream tos(ss);

    // Act
    tos << testString;

    // Assert - the number of newlines in the string, a colon, the string, a newline, but the string
    // has been stripped of the carriage returns.
    EXPECT_EQ(std::string("1:") + testStringWithoutCR + "\n", ss.str());
}


class TextStreamIntegrationTest: public ::testing::Test
{
protected:
    void SetUp() override
    {}

    void TearDown() override
    {}
};

TEST_F(TextStreamIntegrationTest, OutputThenInputSimpleMultiLine)
{
    // Arrange
    std::string multiLineString("One\nTwo\nThree");

    // Act
    std::ostringstream ssO;
    Base::TextOutputStream tos(ssO);
    tos << multiLineString;
    std::istringstream ssI(ssO.str());
    Base::TextInputStream tis(ssI);
    std::string result;
    tis >> result;

    // Assert
    EXPECT_EQ(multiLineString, result);
}

TEST_F(TextStreamIntegrationTest, OutputThenInputMultiLineWithCarriageReturns)
{
    // Arrange
    std::string multiLineString("One\r\nTwo\r\nThree");
    std::string multiLineStringResult("One\nTwo\nThree");

    // Act
    std::ostringstream ssO;
    Base::TextOutputStream tos(ssO);
    tos << multiLineString;
    std::istringstream ssI(ssO.str());
    Base::TextInputStream tis(ssI);
    std::string result;
    tis >> result;

    // Assert
    EXPECT_EQ(multiLineStringResult, result);
}


class StringStreambufTest: public ::testing::Test
{
};

TEST_F(StringStreambufTest, OutputOverwritesAndSeeks)
{
    std::string buffer(4, 'x');
    Base::StringOStreambuf sbuf(buffer);
    std::ostream out(&sbuf);

    out.write("abcd", 4);
    EXPECT_EQ("abcd", buffer);

    out.seekp(2);
    out.write("Z", 1);
    EXPECT_EQ("abZd", buffer);
}

TEST_F(StringStreambufTest, RoundTripBinaryData)
{
    std::string buffer;
    Base::StringOStreambuf obuf(buffer);
    std::ostream out(&obuf);

    const std::string payload("abc\0def", 7);
    out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
    out.seekp(0);
    out.write("X", 1);

    Base::StringIStreambuf ibuf(buffer);
    std::istream in(nullptr);
    in.rdbuf(&ibuf);

    std::string readBack(buffer.size(), '\0');
    in.read(readBack.data(), static_cast<std::streamsize>(readBack.size()));
    EXPECT_EQ(buffer, readBack);

    in.clear();
    in.seekg(3);
    EXPECT_EQ(0, in.get());
}


class PyStreambufTest: public ::testing::Test
{
protected:
    void SetUp() override
    {
        Py_Initialize();
        gilState = PyGILState_Ensure();
    }

    void TearDown() override
    {
        PyErr_Clear();
        PyGILState_Release(gilState);
    }

    // Writes data through a PyStreambuf to a new object of the given io class and returns
    // the value of that object
    static Py::Object writeTo(const char* ioClass, const std::string& data)
    {
        Py::Module io(PyImport_ImportModule("io"), true);
        Py::Object stream = io.callMemberFunction(ioClass);
        {
            Base::PyStreambuf buf(stream.ptr());
            std::ostream out(&buf);
            out.write(data.data(), static_cast<std::streamsize>(data.size()));
        }
        return stream.callMemberFunction("getvalue");
    }

    // Returns a new object of the given io class that holds the given data
    static Py::Object makeStream(const char* ioClass, const Py::Object& data)
    {
        Py::Module io(PyImport_ImportModule("io"), true);
        return io.callMemberFunction(ioClass, Py::TupleN(data));
    }

    // Returns text that is larger than the buffer of the PyStreambuf and doesn't repeat itself
    static std::string numberedLines()
    {
        std::string data;
        for (int i = 1000; i < 1200; ++i) {
            data += std::to_string(i) + "\n";
        }
        return data;
    }

    static std::string readString(std::istream& in, std::streamsize num)
    {
        std::string str(static_cast<std::size_t>(num), '\0');
        in.read(str.data(), num);
        str.resize(static_cast<std::size_t>(in.gcount()));
        return str;
    }

private:
    PyGILState_STATE gilState {};
};

TEST_F(PyStreambufTest, writeBinaryDataToBytesIO)
{
    // Not valid UTF-8 and larger than the buffer of the PyStreambuf
    std::string data;
    for (int i = 0; i < 1000; ++i) {
        data.push_back(static_cast<char>(255 - (i % 256)));
    }

    Py::Object value = writeTo("BytesIO", data);
    ASSERT_TRUE(value.isBytes());
    EXPECT_EQ(Py::Bytes(value).as_std_string(), data);
}

TEST_F(PyStreambufTest, writeTextToBytesIO)
{
    const std::string data("solid box\nendsolid box\n");

    Py::Object value = writeTo("BytesIO", data);
    ASSERT_TRUE(value.isBytes());
    EXPECT_EQ(Py::Bytes(value).as_std_string(), data);
}

TEST_F(PyStreambufTest, writeTextToStringIO)
{
    const std::string data("solid Pi\xc3\xa8" "ce\nendsolid\n");

    Py::Object value = writeTo("StringIO", data);
    ASSERT_TRUE(value.isString());
    EXPECT_EQ(Py::String(value).as_std_string("utf-8"), data);
}

TEST_F(PyStreambufTest, tellAfterPartialRead)
{
    const std::string data = numberedLines();
    Py::Object stream = makeStream("BytesIO", Py::Bytes(data));
    Base::PyStreambuf buf(stream.ptr());
    std::istream in(&buf);

    EXPECT_EQ(readString(in, 10), data.substr(0, 10));
    EXPECT_EQ(static_cast<std::streamoff>(in.tellg()), 10);
    EXPECT_EQ(readString(in, 300), data.substr(10, 300));
    EXPECT_EQ(static_cast<std::streamoff>(in.tellg()), 310);
    // asking for the position doesn't change what is read next
    EXPECT_EQ(readString(in, 10), data.substr(310, 10));
}

TEST_F(PyStreambufTest, seekAfterPartialRead)
{
    const std::string data = numberedLines();
    Py::Object stream = makeStream("BytesIO", Py::Bytes(data));
    Base::PyStreambuf buf(stream.ptr());
    std::istream in(&buf);

    EXPECT_EQ(readString(in, 300), data.substr(0, 300));
    in.seekg(0);
    EXPECT_EQ(readString(in, 20), data.substr(0, 20));
    in.seekg(500);
    EXPECT_EQ(readString(in, 10), data.substr(500, 10));
    EXPECT_EQ(static_cast<std::streamoff>(in.tellg()), 510);
}

TEST_F(PyStreambufTest, seekRelativeAfterPartialRead)
{
    const std::string data = numberedLines();
    Py::Object stream = makeStream("BytesIO", Py::Bytes(data));
    Base::PyStreambuf buf(stream.ptr());
    std::istream in(&buf);

    EXPECT_EQ(readString(in, 10), data.substr(0, 10));
    in.seekg(5, std::ios::cur);
    EXPECT_EQ(static_cast<std::streamoff>(in.tellg()), 15);
    EXPECT_EQ(readString(in, 10), data.substr(15, 10));
    in.seekg(-20, std::ios::cur);
    EXPECT_EQ(readString(in, 10), data.substr(5, 10));
}

TEST_F(PyStreambufTest, seekFromEndAfterPartialRead)
{
    const std::string data = numberedLines();
    const auto size = static_cast<std::streamoff>(data.size());
    Py::Object stream = makeStream("BytesIO", Py::Bytes(data));
    Base::PyStreambuf buf(stream.ptr());
    std::istream in(&buf);

    EXPECT_EQ(readString(in, 10), data.substr(0, 10));
    in.seekg(0, std::ios::end);
    EXPECT_EQ(static_cast<std::streamoff>(in.tellg()), size);
    EXPECT_EQ(in.get(), std::char_traits<char>::eof());
    in.clear();
    in.seekg(-10, std::ios::end);
    EXPECT_EQ(readString(in, 10), data.substr(data.size() - 10));
}

TEST_F(PyStreambufTest, seekBackInStringIO)
{
    const std::string data = numberedLines();
    Py::Object stream = makeStream("StringIO", Py::String(data));
    Base::PyStreambuf buf(stream.ptr());
    std::istream in(&buf);

    EXPECT_EQ(readString(in, 300), data.substr(0, 300));
    in.seekg(0);
    EXPECT_EQ(readString(in, static_cast<std::streamsize>(data.size())), data);
    EXPECT_EQ(in.get(), std::char_traits<char>::eof());
}


// Change this type alias to std::streambuf should still have the tests below pass.
using BufferStreambuf = Base::BufferStreambuf;

TEST(BufferStreambuf, emptyBufferIn)
{
    std::array<char, 0> array;
    BufferStreambuf streambuf(array, std::ios::in);
    std::istream stream(&streambuf);

    // Read a byte with get()
    EXPECT_TRUE(stream.good());
    EXPECT_EQ(stream.get(), std::istream::traits_type::eof());
    EXPECT_TRUE(stream.eof());
    EXPECT_TRUE(stream.fail());

    // Peek a byte
    stream.seekg(0, std::ios::beg);
    stream.clear();
    EXPECT_TRUE(stream.good());
    EXPECT_EQ(stream.peek(), std::istream::traits_type::eof());
    EXPECT_TRUE(stream.eof());
    EXPECT_FALSE(stream.fail());

    // Read a char with formatted input
    stream.seekg(0, std::ios::beg);
    stream.clear();
    EXPECT_TRUE(stream.good());
    char c = 123;
    stream >> c;
    EXPECT_EQ(c, 123);
    EXPECT_TRUE(stream.eof());
    EXPECT_TRUE(stream.fail());
}

TEST(BufferStreambuf, emptyBufferOut)
{
    std::array<char, 0> array;
    BufferStreambuf streambuf(array, std::ios::out);
    std::ostream stream(&streambuf);

    // put() a char
    EXPECT_TRUE(stream.good());
    stream.put('a');
    EXPECT_TRUE(stream.fail());

    // write() a string
    stream.seekp(0, std::ios::beg);
    stream.clear();
    EXPECT_TRUE(stream.good());
    stream.write("ab", 2);
    EXPECT_TRUE(stream.fail());

    // Insert a string with formatted output
    stream.seekp(0, std::ios::beg);
    stream.clear();
    EXPECT_TRUE(stream.good());
    stream << "test";
    EXPECT_TRUE(stream.fail());
}

TEST(BufferStreambuf, bufferIn)  // codespell:ignore bufferin
{
    auto array = std::to_array("h\0ello\nline2\r\nline3|9");
    BufferStreambuf streambuf(array, std::ios::in);
    std::istream stream(&streambuf);

    // Check stream size matches the buffer size
    EXPECT_TRUE(stream.good());
    stream.seekg(0, std::ios::end);
    EXPECT_EQ(stream.tellg(), array.size());
    stream.seekg(0, std::ios::beg);

    // Read bytes with get()
    EXPECT_TRUE(stream.good());
    EXPECT_EQ(stream.get(), 'h');
    EXPECT_TRUE(stream.good());
    EXPECT_EQ(stream.get(), '\0');
    EXPECT_TRUE(stream.good());

    // Extract strings with formatted input
    stream.seekg(5, std::ios::beg);
    std::string line;
    stream >> line;
    EXPECT_EQ(line, "o");
    stream >> line;
    EXPECT_EQ(line, "line2");

    // Extract strings with getline()
    std::array<char, 8> aline;
    stream.getline(aline.data(), aline.size(), '|');
    EXPECT_EQ(aline[0], '\r');
    EXPECT_EQ(aline[1], '\n');
    EXPECT_EQ(aline[6], '3');
    EXPECT_EQ(aline[7], '\0');
    EXPECT_FALSE(stream.eof());

    // Extract numbers with formatted input
    unsigned int number = -1;
    stream >> number;
    EXPECT_EQ(number, 9);
    EXPECT_FALSE(stream.fail());
    EXPECT_EQ(stream.get(), '\0');  // Consume string literal null terminator
    EXPECT_FALSE(stream.fail());
    EXPECT_FALSE(stream.eof());
    stream >> number;
    // [istream.formatted.reqmts] precludes the formatted input from working at all when
    // at eof because the "sentry" object will signal failure before conversion is attempted.
    // `number` is therefore left untouched, and the fail & eof bits set as usual.
    EXPECT_EQ(number, 9);
    EXPECT_TRUE(stream.fail());
    EXPECT_TRUE(stream.eof());

    // Seek to and then go before begin
    stream.clear();
    stream.seekg(0, std::ios::beg);
    stream.seekg(-8, std::ios::cur);
    EXPECT_EQ(stream.tellg(), -1);
    EXPECT_TRUE(stream.fail());
    // Seek to and then go past end
    stream.clear();
    stream.seekg(array.size(), std::ios::beg);
    EXPECT_EQ(stream.tellg(), array.size());
    stream.seekg(1, std::ios::cur);
    EXPECT_EQ(stream.tellg(), -1);
    EXPECT_TRUE(stream.fail());
}

TEST(BufferStreambuf, bufferOut)
{
    std::array<char, 12> array;
    BufferStreambuf streambuf(array, std::ios::out | std::ios::ate);
    std::ostream stream(&streambuf);

    // Expect to start at end of array
    EXPECT_TRUE(stream.good());
    EXPECT_EQ(stream.tellp(), array.size());
    // Seek past the end at once
    stream.seekp(array.size() + 4, std::ios::cur);
    EXPECT_EQ(stream.tellp(), -1);
    EXPECT_TRUE(stream.fail());
    // Seek to std::ios::end, which is by definition *not* the buffer end in out-only mode
    // but the current cursor position ([spanbuf.virtuals] 4.3.1)
    stream.clear();
    stream.seekp(3, std::ios::beg);
    stream.seekp(0, std::ios::end);
    EXPECT_EQ(stream.tellp(), 3);
    // Seek to and then go before begin
    stream.clear();
    stream.seekp(0, std::ios::beg);
    stream.seekp(-8, std::ios::cur);
    EXPECT_EQ(stream.tellp(), -1);
    EXPECT_TRUE(stream.fail());
    // Seek to and then go past end
    stream.clear();
    stream.seekp(array.size(), std::ios::beg);
    EXPECT_EQ(stream.tellp(), array.size());
    stream.seekp(1, std::ios::cur);
    EXPECT_EQ(stream.tellp(), -1);
    EXPECT_TRUE(stream.fail());

    // Insert a byte with put()
    stream.clear();
    stream.seekp(0, std::ios::beg);
    stream.put('a');
    EXPECT_EQ(array[0], 'a');

    // Insert strings with formatted output
    stream << "123\n456";
    EXPECT_EQ(array[1], '1');
    EXPECT_EQ(array[4], '\n');
    EXPECT_EQ(array[5], '4');
    stream << "z";
    EXPECT_EQ(array[8], 'z');

    // Insert numbers with formatted output
    stream << 89;
    EXPECT_EQ(array[9], '8');
    EXPECT_EQ(array[10], '9');

    // Insert a string and then overflow the buffer
    stream.write("eof", 3);
    stream.put('X');
    EXPECT_TRUE(stream.fail());

    // Insert a string to overflow the buffer at once
    stream.clear();
    stream.seekp(array.size() - 2, std::ios::beg);
    stream.write("EOF", 3);
    EXPECT_TRUE(stream.fail());
}
