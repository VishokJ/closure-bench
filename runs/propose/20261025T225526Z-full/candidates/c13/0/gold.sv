`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b1;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int   n_valid = 0;
  int   n_err = 0;
  logic [7:0] got;

  always @(negedge clk) begin
    if (!rst) begin
      if (m_axis_tvalid) begin got = m_axis_tdata; n_valid++; end
      if (frame_error || overrun_error) n_err++;
    end
  end

  task automatic send_byte(input logic [7:0] b);
    rxd = 1'b0; repeat (40) @(negedge clk);
    for (int i = 0; i < 8; i++) begin rxd = b[i]; repeat (40) @(negedge clk); end
    rxd = 1'b1; repeat (40) @(negedge clk);
  endtask

  int  cnt;
  bit  fell;
  initial begin
    repeat (3) @(negedge clk);
    rst = 1'b0;
    repeat (5) @(negedge clk);
    if (busy) $fatal(1, "busy high while idle");

    // False start: rxd low for 19 clocks, rejected at mid-start-bit check
    rxd = 1'b0;
    cnt = 0; fell = 0;
    for (int i = 0; i < 100; i++) begin
      @(negedge clk);
      if (i == 18) rxd = 1'b1;
      if (busy) begin
        if (fell) $fatal(1, "busy re-asserted after false start");
        cnt++;
      end else if (cnt > 0) fell = 1;
    end
    if (cnt != 20) $fatal(1, "busy high for %0d clocks, expected 20 (4*prescale)", cnt);
    if (busy) $fatal(1, "busy not released after false start");
    if (n_valid != 0) $fatal(1, "false start produced a word");
    if (n_err != 0) $fatal(1, "false start produced an error strobe");

    // Receiver still works afterwards
    send_byte(8'hA5);
    repeat (20) @(negedge clk);
    if (n_valid != 1) $fatal(1, "expected 1 word, got %0d", n_valid);
    if (got !== 8'hA5) $fatal(1, "got 0x%02h expected 0xA5", got);
    if (n_err != 0) $fatal(1, "unexpected error strobe");
    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
